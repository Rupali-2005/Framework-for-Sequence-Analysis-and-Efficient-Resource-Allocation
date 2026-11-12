from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
import hmac
import json
from math import isfinite
import os
from threading import Lock, Thread
from uuid import uuid4

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from charts import dashboard_chart, dataset_chart
from kmp import find_all
from metrics import calculate
from models import Machine, Process
from scheduling import SUPPORTED_ALGORITHMS, simulate
import storage
from mysql import connector


load_dotenv()
app = Flask(__name__, static_folder="../frontend", static_url_path="")
app.secret_key = os.getenv("FLASK_SECRET_KEY") or os.urandom(32)
MAX_UPLOAD_FILE_SIZE = 5 * 1024 * 1024
MAX_BATCH_FILES = 10
app.config["MAX_CONTENT_LENGTH"] = (
    2 * MAX_UPLOAD_FILE_SIZE * MAX_BATCH_FILES + 64 * 1024
)

ROLE_PRIORITIES = {
    "professor": 1,
    "management": 2,
    "student": 3,
}
LOGIN_ACCOUNTS = {
    role: {
        "username": os.getenv(f"{role.upper()}_USERNAME") or role,
        "password": os.getenv(f"{role.upper()}_PASSWORD") or "",
    }
    for role in ROLE_PRIORITIES
}

machines: list[Machine] = []
processes: list[Process] = []
next_machine_id = 1
next_process_id = 1
DEFAULT_TIME_QUANTUM = 2.0
simulation_lock = Lock()
storage_initialization_lock = Lock()
storage_initialized = False
simulation_state = {
    "id": None,
    "status": "idle",
    "result": None,
    "error": None,
}


@app.before_request
def initialize_database():
    global machines, processes
    global next_machine_id, next_process_id, storage_initialized

    if storage_initialized:
        return None

    with storage_initialization_lock:
        if storage_initialized:
            return None
        try:
            loaded_machines, loaded_processes = storage.initialize()
        except (connector.Error, ValueError):
            app.logger.exception("Could not initialize MySQL persistence")
            return jsonify(
                error=(
                    "Database unavailable or invalid. Start MySQL, check "
                    "MYSQL_* settings, and verify the PBL schema."
                )
            ), 503

        machines = loaded_machines
        processes = loaded_processes
        next_machine_id = storage.next_machine_id()
        next_process_id = storage.next_process_id()
        storage_initialized = True

    return None


@app.errorhandler(connector.Error)
def database_error(error):
    app.logger.exception("MySQL operation failed", exc_info=error)
    return jsonify(error="Database operation failed; no data was saved."), 503


@app.errorhandler(RequestEntityTooLarge)
def request_too_large(_error):
    return jsonify(error="Batch upload exceeds the maximum request size"), 413


def _signature_results(process: Process) -> list[dict]:
    if process.status != "Completed":
        return []
    signatures = process.patterns or [
        {"name": process.pattern, "pattern": process.pattern}
    ]
    return [
        {
            "name": signature["name"],
            "matches": len(process.signature_matches[index])
            if index < len(process.signature_matches)
            else 0,
            "match_positions": (
                process.signature_matches[index]
                if index < len(process.signature_matches)
                else []
            ),
        }
        for index, signature in enumerate(signatures)
    ]


def process_dict(process: Process) -> dict:
    return {
        "id": process.id,
        "name": process.name,
        "sequence": process.sequence,
        "pattern": process.pattern,
        "priority": process.priority,
        "work_units": process.work_units,
        "matches": len(process.matches) if process.status == "Completed" else None,
        "match_positions": process.matches if process.status == "Completed" else [],
        "signature_results": _signature_results(process),
        "sequence_filename": process.sequence_filename,
        "sequence_size": process.sequence_size,
        "pattern_filename": process.pattern_filename,
        "pattern_size": process.pattern_size,
        "content_available": bool(process.sequence and process.pattern),
        "allocated_vm": process.allocated_vm,
        "estimated_time": process.estimated_time,
        "status": process.status,
    }


def machine_dict(machine: Machine) -> dict:
    return {
        "id": machine.id,
        "name": machine.name,
        "capacity": machine.capacity,
        "queue": machine.ready_queue,
    }


def estimate_time(
    sequence: str,
    capacity: int | None,
    pattern_count: int = 1,
) -> float | None:
    if capacity is None:
        return None
    return round(len(sequence) * pattern_count / capacity, 2)


def current_process_state() -> list[dict]:
    return [process_dict(process) for process in processes]


def request_data() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def login_required(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        if session.get("role") not in ROLE_PRIORITIES:
            return jsonify(error="Please log in to continue"), 401
        return handler(*args, **kwargs)

    return wrapped


def parse_time_quantum(data: dict) -> float:
    try:
        time_quantum = float(data.get("time_quantum", DEFAULT_TIME_QUANTUM))
    except (TypeError, ValueError):
        raise ValueError("Time quantum must be a positive number") from None

    if not isfinite(time_quantum) or time_quantum <= 0:
        raise ValueError("Time quantum must be a positive number")

    return time_quantum


def _file_metadata(data: dict, key: str) -> tuple[str | None, int | None]:
    metadata = data.get(key)
    if metadata is None:
        return None, None
    if not isinstance(metadata, dict):
        raise ValueError("Invalid uploaded file metadata")

    filename = metadata.get("filename")
    size = metadata.get("size")
    if (
        not isinstance(filename, str)
        or not filename.strip()
        or not isinstance(size, int)
        or isinstance(size, bool)
        or size < 0
    ):
        raise ValueError("Invalid uploaded file metadata")

    cleaned_filename = secure_filename(filename)[:255]
    if not cleaned_filename:
        raise ValueError("Invalid uploaded file name")
    return cleaned_filename, size


def _build_process(data: dict, process_id: int, role: str) -> Process:
    raw_patterns = data.get("patterns")
    sequence_is_binary = data.get("sequence_binary") is True
    raw_sequence = str(data["sequence"])
    if sequence_is_binary or raw_patterns is not None:
        sequence = raw_sequence
    else:
        sequence = "".join(raw_sequence.split()).upper()
    pattern = str(data["pattern"])
    patterns = []
    if raw_patterns is None:
        pattern = pattern.upper()
    else:
        if not isinstance(raw_patterns, list) or not raw_patterns:
            raise ValueError("Provide valid process fields")
        for item in raw_patterns:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("name"), str)
                or not isinstance(item.get("pattern"), str)
            ):
                raise ValueError("Provide valid process fields")
            signature = item["pattern"].strip()
            if not signature or not signature.isascii():
                raise ValueError("Provide valid process fields")
            patterns.append(
                {"name": item["name"].strip() or signature, "pattern": signature}
            )
        pattern = patterns[0]["pattern"]

    given_priority = int(data["priority"])
    sequence_filename, sequence_size = _file_metadata(data, "sequence_file")
    pattern_filename, pattern_size = _file_metadata(data, "pattern_file")
    process = Process(
        id=process_id,
        name=str(data["name"]).strip(),
        sequence=sequence,
        pattern=pattern,
        priority=round((given_priority + ROLE_PRIORITIES[role]) / 2, 2),
        work_units=len(sequence) * (len(patterns) or 1),
        patterns=patterns,
        sequence_filename=sequence_filename,
        sequence_size=sequence_size,
        pattern_filename=pattern_filename,
        pattern_size=pattern_size,
    )
    if not process.name or len(process.name) > 100 or not sequence or not pattern:
        raise ValueError("Provide valid process fields")
    if sequence_is_binary and any(ord(character) > 255 for character in sequence):
        raise ValueError("Provide valid process fields")
    if given_priority < 1:
        raise ValueError("Provide valid process fields")
    return process


@app.route("/")
def home():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/state")
@login_required
def state():
    global next_machine_id, next_process_id
    if simulation_state["status"] != "running":
        loaded_machines, loaded_processes = storage.load_state()
        machines[:] = loaded_machines
        loaded_ids = {process.id for process in loaded_processes}
        runtime_processes = [
            process
            for process in processes
            if process.id not in loaded_ids and process.sequence and process.pattern
        ]
        processes[:] = sorted(
            [*loaded_processes, *runtime_processes],
            key=lambda process: process.id,
        )
        next_machine_id = storage.next_machine_id()
        next_process_id = storage.next_process_id()
    return jsonify(
        machines=[machine_dict(machine) for machine in machines],
        processes=[process_dict(process) for process in processes],
    )


@app.route("/api/dataset")
@login_required
def dataset():
    dataset_records = storage.load_dataset()
    current_by_id = {process.id: process for process in processes}
    for record in dataset_records:
        process = current_by_id.get(record["id"])
        if process is not None:
            record.update(process_dict(process))
            record["content_available"] = True
    return jsonify(
        processes=dataset_records,
        chart=dataset_chart(dataset_records),
    )


@app.route("/api/auth/status")
def auth_status():
    role = session.get("role")
    if role not in ROLE_PRIORITIES:
        return jsonify(authenticated=False)
    return jsonify(
        authenticated=True,
        role=role,
        role_priority=ROLE_PRIORITIES[role],
    )


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request_data()
    username = data.get("username")
    password = data.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify(error="Username and password are required"), 400

    for role, credentials in LOGIN_ACCOUNTS.items():
        if (
            credentials["password"]
            and hmac.compare_digest(
                username.encode("utf-8"),
                credentials["username"].encode("utf-8"),
            )
            and hmac.compare_digest(
                password.encode("utf-8"),
                credentials["password"].encode("utf-8"),
            )
        ):
            session.clear()
            session["role"] = role
            return jsonify(
                authenticated=True,
                role=role,
                role_priority=ROLE_PRIORITIES[role],
            )
    return jsonify(error="Invalid username or password"), 401


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify(authenticated=False)


@app.route("/api/machines", methods=["POST"])
@login_required
def add_machine():
    global next_machine_id
    data = request_data()

    if simulation_state["status"] == "running":
        return jsonify(error="Cannot add a machine while simulation is running"), 409

    try:
        machine = Machine(
            id=next_machine_id,
            name=str(data["name"]).strip(),
            capacity=int(data["capacity"]),
        )
        if not machine.name or len(machine.name) > 100 or machine.capacity < 1:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return jsonify(error="Name and positive capacity are required"), 400

    storage.save_machine(machine)
    next_machine_id += 1
    machines.append(machine)
    for process in processes:
        if process.status == "Queued":
            process.estimated_time = estimate_time(
                process.sequence,
                max(item.capacity for item in machines),
                len(process.patterns) or 1,
            )
            storage.save_process(process)
    return jsonify(machine_dict(machine)), 201


@app.route("/api/machines/<int:machine_id>", methods=["PUT"])
@login_required
def update_machine(machine_id: int):
    if simulation_state["status"] == "running":
        return jsonify(error="Cannot edit a machine while simulation is running"), 409

    machine = next((item for item in machines if item.id == machine_id), None)
    if machine is None:
        return jsonify(error="Virtual machine not found"), 404

    data = request_data()
    try:
        name = str(data["name"]).strip()
        capacity = int(data["capacity"])
        if not name or len(name) > 100 or capacity < 1:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return jsonify(error="Name and positive capacity are required"), 400

    updated = Machine(
        id=machine.id,
        name=name,
        capacity=capacity,
        ready_queue=machine.ready_queue,
        busy_until=machine.busy_until,
    )
    storage.save_machine(updated)
    machine.name = updated.name
    machine.capacity = updated.capacity
    _refresh_queued_estimates()
    return jsonify(machine_dict(machine))


@app.route("/api/machines/<int:machine_id>", methods=["DELETE"])
@login_required
def delete_machine(machine_id: int):
    if simulation_state["status"] == "running":
        return jsonify(error="Cannot delete a machine while simulation is running"), 409

    machine = next((item for item in machines if item.id == machine_id), None)
    if machine is None:
        return jsonify(error="Virtual machine not found"), 404

    storage.delete_machine(machine_id)
    machines.remove(machine)
    _refresh_queued_estimates()
    return jsonify(deleted=True, id=machine_id)


def _refresh_queued_estimates() -> None:
    fastest_capacity = max(
        (machine.capacity for machine in machines),
        default=None,
    )
    for process in processes:
        if process.status == "Queued":
            process.estimated_time = estimate_time(
                process.sequence,
                fastest_capacity,
                len(process.patterns) or 1,
            )
            storage.save_process(process)


@app.route("/api/processes", methods=["POST"])
@login_required
def add_process():
    global next_process_id
    data = request_data()

    if simulation_state["status"] == "running":
        return jsonify(error="Cannot add a process while simulation is running"), 409

    try:
        process = _build_process(data, next_process_id, session["role"])
    except (KeyError, TypeError, ValueError):
        return jsonify(error="Provide valid process fields"), 400

    if machines:
        process.estimated_time = estimate_time(
            process.sequence,
            max(machine.capacity for machine in machines),
            len(process.patterns) or 1,
        )

    storage.save_process(process)
    next_process_id += 1
    processes.append(process)
    return jsonify(process_dict(process)), 201


@app.route("/api/processes/batch", methods=["POST"])
@login_required
def add_process_batch():
    global next_process_id
    data = request_data()

    if simulation_state["status"] == "running":
        return jsonify(error="Cannot add processes while simulation is running"), 409

    sequences = data.get("sequences")
    if (
        not isinstance(sequences, list)
        or not sequences
        or len(sequences) > MAX_BATCH_FILES
    ):
        return jsonify(
            error=f"Submit between 1 and {MAX_BATCH_FILES} sequence files"
        ), 400

    base_name = data.get("name")
    if not isinstance(base_name, str) or not base_name.strip():
        return jsonify(error="A process name is required"), 400

    built_processes = []
    try:
        for offset, sequence_data in enumerate(sequences):
            if not isinstance(sequence_data, dict):
                raise ValueError
            source_metadata = sequence_data.get("sequence_file")
            source_name = (
                source_metadata.get("filename")
                if isinstance(source_metadata, dict)
                else None
            )
            process_name = base_name.strip()
            if len(sequences) > 1 and isinstance(source_name, str) and source_name:
                process_name = f"{process_name} - {source_name}"[:100]
            process_data = {
                **data,
                **sequence_data,
                "name": process_name,
            }
            built_processes.append(
                _build_process(
                    process_data,
                    next_process_id + offset,
                    session["role"],
                )
            )
    except (KeyError, TypeError, ValueError):
        return jsonify(error="Provide valid process fields for every file"), 400

    for process in built_processes:
        if machines:
            process.estimated_time = estimate_time(
                process.sequence,
                max(machine.capacity for machine in machines),
                len(process.patterns) or 1,
            )

    storage.save_processes(built_processes)
    next_process_id += len(built_processes)
    processes.extend(built_processes)
    return jsonify(
        processes=[process_dict(process) for process in built_processes]
    ), 201


@app.route("/api/processes/<int:process_id>/reset", methods=["POST"])
@login_required
def reset_process(process_id: int):
    if simulation_state["status"] == "running":
        return jsonify(error="Cannot reset a process while simulation is running"), 409

    process = next((item for item in processes if item.id == process_id), None)
    if process is None:
        return jsonify(
            error="Process not found or its uploaded content is unavailable"
        ), 404
    if process.status not in {"Completed", "Failed"}:
        return jsonify(error="Only completed or failed processes can be requeued"), 409

    process.status = "Queued"
    process.matches = []
    process.signature_matches = []
    process.allocated_vm = None
    process.estimated_time = estimate_time(
        process.sequence,
        max((machine.capacity for machine in machines), default=None),
        len(process.patterns) or 1,
    )
    storage.save_process(process)
    return jsonify(process_dict(process))


@app.route("/api/processes/upload", methods=["POST"])
@login_required
def upload_process_file():
    target = request.form.get("target", "sequence")
    if target not in {"sequence", "pattern"}:
        return jsonify(error="Upload target must be sequence or pattern"), 400

    uploaded_files = request.files.getlist("files")
    if not uploaded_files:
        uploaded_file = request.files.get("file")
        if uploaded_file is not None:
            uploaded_files = [uploaded_file]
    if not uploaded_files or any(not item.filename for item in uploaded_files):
        return jsonify(error="Choose a file to upload"), 400
    if len(uploaded_files) > MAX_BATCH_FILES:
        return jsonify(error=f"Upload no more than {MAX_BATCH_FILES} files"), 400
    if target == "pattern" and len(uploaded_files) != 1:
        return jsonify(error="Upload one pattern file for the batch"), 400

    contents_by_file = []
    for uploaded_file in uploaded_files:
        contents = uploaded_file.read(MAX_UPLOAD_FILE_SIZE + 1)
        if len(contents) > MAX_UPLOAD_FILE_SIZE:
            return jsonify(
                error=f"{uploaded_file.filename} exceeds the 5 MB file limit"
            ), 413
        filename = secure_filename(uploaded_file.filename) or "uploaded-file"
        contents_by_file.append(
            (
                uploaded_file,
                contents,
                {"filename": filename, "size": len(contents)},
            )
        )

    uploaded_file, contents, file_metadata = contents_by_file[0]

    if target == "pattern":
        try:
            text = contents.decode("utf-8-sig")
        except UnicodeDecodeError:
            return jsonify(error="Pattern files must contain UTF-8 text or JSON"), 400
        try:
            document = json.loads(text)
        except json.JSONDecodeError:
            if uploaded_file.filename.lower().endswith(".json"):
                return jsonify(error="Pattern JSON file is not valid JSON"), 400
            if not text.strip():
                return jsonify(error="File is empty"), 400
            return jsonify(sequence=text, file=file_metadata)

        signature_items = document.get("signatures") if isinstance(document, dict) else None
        if not isinstance(signature_items, list) or not signature_items:
            return jsonify(
                error="JSON pattern file must contain a non-empty signatures array"
            ), 400
        signatures = []
        for item in signature_items:
            if not isinstance(item, dict):
                return jsonify(error="Each JSON signature must be an object"), 400
            name = item.get("name")
            pattern = item.get("pattern_ascii")
            if (
                not isinstance(pattern, str)
                or not pattern
                or not pattern.isascii()
            ):
                return jsonify(
                    error=(
                        "Each JSON signature needs a non-empty ASCII "
                        "pattern_ascii value"
                    )
                ), 400
            signatures.append(
                {
                    "name": (
                        name.strip()
                        if isinstance(name, str) and name.strip()
                        else pattern
                    ),
                    "pattern": pattern,
                }
            )
        return jsonify(patterns=signatures, file=file_metadata)

    sequences = []
    for uploaded_file, contents, metadata in contents_by_file:
        if uploaded_file.filename.lower().endswith(".bin"):
            sequence = contents.decode("latin-1")
            binary = True
        else:
            try:
                sequence = contents.decode("utf-8-sig")
            except UnicodeDecodeError:
                return jsonify(
                    error=f"{uploaded_file.filename} must contain UTF-8 text"
                ), 400
            if not sequence.strip():
                return jsonify(error=f"{uploaded_file.filename} is empty"), 400
            binary = False
        sequences.append(
            {
                "sequence": sequence,
                "binary": binary,
                "file": metadata,
            }
        )

    if len(sequences) == 1:
        return jsonify(
            sequence=sequences[0]["sequence"],
            binary=sequences[0]["binary"],
            file=sequences[0]["file"],
        )
    return jsonify(sequences=sequences)


def run_simulation(
    algorithm: str,
    time_quantum: float,
    run_machines: list[Machine],
    run_processes: list[Process],
) -> dict:
    allocations, machine_data = simulate(
        run_machines,
        run_processes,
        algorithm,
        time_quantum,
    )
    metrics = calculate(allocations, machine_data)
    return {
        "algorithm": algorithm,
        "allocations": allocations,
        "machines": machine_data,
        "processes": [process_dict(process) for process in run_processes],
        "metrics": metrics,
    }


@app.route("/api/simulate", methods=["POST"])
@login_required
def simulation():
    data = request_data()
    algorithm = str(data.get("algorithm", "FCFS")).upper()
    if algorithm not in SUPPORTED_ALGORITHMS:
        return jsonify(error="Unknown algorithm"), 400

    try:
        time_quantum = parse_time_quantum(data)
    except ValueError as error:
        return jsonify(error=str(error)), 400

    with simulation_lock:
        if simulation_state["status"] == "running":
            return jsonify(error="A simulation is already running"), 409
        if not machines:
            return jsonify(error="Add at least one virtual machine"), 400
        queued_processes = [
            process for process in processes if process.status == "Queued"
        ]
        if not queued_processes:
            return jsonify(error="There are no queued processes to simulate"), 400

        try:
            result = run_simulation(
                algorithm,
                time_quantum,
                deepcopy(machines),
                deepcopy(queued_processes),
            )
        except ValueError as error:
            return jsonify(error=str(error)), 400

        process_by_id = {process.id: process for process in queued_processes}
        machine_capacities = {machine.id: machine.capacity for machine in machines}
        for allocation in result["allocations"]:
            process = process_by_id[allocation["process_id"]]
            process.estimated_time = estimate_time(
                process.sequence,
                machine_capacities[allocation["machine_id"]],
                len(process.patterns) or 1,
            )
        for process in queued_processes:
            storage.save_process(process)

        run_id = str(uuid4())
        simulation_state.update(
            id=run_id,
            status="running",
            result=None,
            error=None,
        )
        Thread(
            target=execute_processes,
            args=(run_id, result, machine_capacities),
            daemon=True,
        ).start()

    return jsonify(run_id=run_id, status="running"), 202


def execute_processes(
    run_id: str,
    result: dict,
    machine_capacities: dict[int, int],
) -> None:
    process_by_id = {process.id: process for process in processes}

    try:
        allocations_by_machine = {
            machine_id: [] for machine_id in machine_capacities
        }
        for allocation in result["allocations"]:
            allocations_by_machine[allocation["machine_id"]].append(allocation)

        def execute_machine_queue(machine_allocations: list[dict]) -> None:
            for allocation in machine_allocations:
                process = process_by_id[allocation["process_id"]]
                process.status = "Processing"
                process.allocated_vm = allocation["machine"]
                storage.save_process(process)
                patterns = process.patterns or [
                    {"name": process.pattern, "pattern": process.pattern}
                ]
                process.signature_matches = [
                    find_all(
                        process.sequence,
                        signature["pattern"],
                        comparison_capacity=machine_capacities[
                            allocation["machine_id"]
                        ],
                    )
                    for signature in patterns
                ]
                process.matches = [
                    position
                    for positions in process.signature_matches
                    for position in positions
                ]
                process.status = "Completed"
                storage.save_process(process)

        with ThreadPoolExecutor(max_workers=len(machine_capacities)) as executor:
            futures = [
                executor.submit(execute_machine_queue, machine_allocations)
                for machine_allocations in allocations_by_machine.values()
                if machine_allocations
            ]
            for future in futures:
                future.result()

        for machine_result in result["machines"]:
            machine = next(
                item for item in machines if item.id == machine_result["id"]
            )
            machine.ready_queue = machine_result["ready_queue"]
            machine.busy_until = machine_result["busy_until"]

        result["processes"] = current_process_state()
        result["machines"] = [
            {
                "id": machine.id,
                "name": machine.name,
                "capacity": machine.capacity,
                "ready_queue": machine.ready_queue,
                "busy_until": machine.busy_until,
            }
            for machine in machines
        ]
        storage.save_run(
            result["algorithm"],
            result["metrics"],
            result["allocations"],
        )
        with simulation_lock:
            if simulation_state["id"] == run_id:
                simulation_state.update(status="completed", result=result)
    except Exception as error:
        app.logger.exception("Simulation persistence or execution failed")
        active_processes = [
            process for process in processes if process.status == "Processing"
        ]
        for active_process in active_processes:
            active_process.status = "Failed"
            try:
                storage.save_process(active_process)
            except connector.Error:
                app.logger.exception("Could not persist failed process status")
        with simulation_lock:
            if simulation_state["id"] == run_id:
                simulation_state.update(
                    status="failed",
                    error="Simulation failed; check the server log for details.",
                )


@app.route("/api/simulation/<run_id>")
@login_required
def simulation_status(run_id: str):
    with simulation_lock:
        if simulation_state["id"] != run_id:
            return jsonify(error="Simulation not found"), 404

        response = {
            "run_id": run_id,
            "status": simulation_state["status"],
            "processes": current_process_state(),
            "machines": [machine_dict(machine) for machine in machines],
        }
        if simulation_state["status"] == "completed":
            response["result"] = simulation_state["result"]
        elif simulation_state["status"] == "failed":
            response["error"] = simulation_state["error"]

    return jsonify(response)


@app.route("/api/compare", methods=["POST"])
@login_required
def compare():
    queued_processes = [
        process for process in processes if process.status == "Queued"
    ]
    if not queued_processes:
        return jsonify(error="There are no queued processes to compare"), 400

    try:
        time_quantum = parse_time_quantum(request_data())
    except ValueError as error:
        return jsonify(error=str(error)), 400

    results = {}
    for algorithm in ("FCFS", "SJF", "PRIORITY", "RR", "SRTF"):
        try:
            result = run_simulation(
                algorithm,
                time_quantum,
                deepcopy(machines),
                deepcopy(queued_processes),
            )
        except ValueError as error:
            return jsonify(error=str(error)), 400
        results[algorithm] = result["metrics"]
        storage.save_run(
            algorithm,
            result["metrics"],
            result["allocations"],
        )

    return jsonify(
        results=results,
        chart=dashboard_chart(results),
    )


if __name__ == "__main__":
    app.run(debug=True)
