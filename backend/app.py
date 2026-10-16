from copy import deepcopy
from math import isfinite
from threading import Lock, Thread
from uuid import uuid4

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

from charts import dashboard_chart
from kmp import find_all
from metrics import calculate
from models import Machine, Process
from scheduling import SUPPORTED_ALGORITHMS, simulate
import storage
from mysql import connector


load_dotenv()
app = Flask(__name__, static_folder="../frontend", static_url_path="")

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
        next_machine_id = max((machine.id for machine in machines), default=0) + 1
        next_process_id = max((process.id for process in processes), default=0) + 1
        storage_initialized = True

    return None


@app.errorhandler(connector.Error)
def database_error(error):
    app.logger.exception("MySQL operation failed", exc_info=error)
    return jsonify(error="Database operation failed; no data was saved."), 503


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


def estimate_time(sequence: str, capacity: int | None) -> float | None:
    if capacity is None:
        return None
    return round(len(sequence) / capacity, 2)


def current_process_state() -> list[dict]:
    return [process_dict(process) for process in processes]


def request_data() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def parse_time_quantum(data: dict) -> float:
    try:
        time_quantum = float(data.get("time_quantum", DEFAULT_TIME_QUANTUM))
    except (TypeError, ValueError):
        raise ValueError("Time quantum must be a positive number") from None

    if not isfinite(time_quantum) or time_quantum <= 0:
        raise ValueError("Time quantum must be a positive number")

    return time_quantum


@app.route("/")
def home():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/state")
def state():
    return jsonify(
        machines=[machine_dict(machine) for machine in machines],
        processes=[process_dict(process) for process in processes],
    )


@app.route("/api/machines", methods=["POST"])
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
        if not machine.name or machine.capacity < 1:
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
            )
            storage.save_process(process)
    return jsonify(machine_dict(machine)), 201


@app.route("/api/processes", methods=["POST"])
def add_process():
    global next_process_id
    data = request_data()

    if simulation_state["status"] == "running":
        return jsonify(error="Cannot add a process while simulation is running"), 409

    try:
        sequence = str(data["sequence"]).replace(" ", "").upper()
        pattern = str(data["pattern"]).upper()
        process = Process(
            id=next_process_id,
            name=str(data["name"]).strip(),
            sequence=sequence,
            pattern=pattern,
            priority=int(data["priority"]),
            work_units=int(data["work_units"]),
        )
        if not process.name or not sequence or not pattern:
            raise ValueError
        if process.priority < 1 or process.work_units < 1:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return jsonify(error="Provide valid process fields"), 400

    if machines:
        process.estimated_time = estimate_time(
            process.sequence,
            max(machine.capacity for machine in machines),
        )

    storage.save_process(process)
    next_process_id += 1
    processes.append(process)
    return jsonify(process_dict(process)), 201


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
        if not processes:
            return jsonify(error="Add at least one process"), 400

        for process in processes:
            process.status = "Queued"
            process.matches = []

        try:
            result = run_simulation(
                algorithm,
                time_quantum,
                deepcopy(machines),
                deepcopy(processes),
            )
        except ValueError as error:
            return jsonify(error=str(error)), 400

        process_by_id = {process.id: process for process in processes}
        machine_capacities = {machine.id: machine.capacity for machine in machines}
        for allocation in result["allocations"]:
            process = process_by_id[allocation["process_id"]]
            process.estimated_time = estimate_time(
                process.sequence,
                machine_capacities[allocation["machine_id"]],
            )
        for process in processes:
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
        for allocation in result["allocations"]:
            process = process_by_id[allocation["process_id"]]
            process.status = "Processing"
            storage.save_process(process)
            process.matches = find_all(
                process.sequence,
                process.pattern,
                comparison_capacity=machine_capacities[allocation["machine_id"]],
            )
            process.status = "Completed"
            storage.save_process(process)

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
        active_process = next(
            (
                process
                for process in processes
                if process.status == "Processing"
            ),
            None,
        )
        if active_process:
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
def compare():
    if not processes:
        return jsonify(error="Add at least one process"), 400

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
                deepcopy(processes),
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
