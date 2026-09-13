import os
from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv
from models import Machine, Process
from scheduling import simulate
from metrics import calculate
from storage import save_machine, save_process, save_run

load_dotenv()
app = Flask(__name__, static_folder="../frontend", static_url_path="")
machines: list[Machine] = []
processes: list[Process] = []
next_machine_id = next_process_id = 1

def process_dict(p):
    return {"id": p.id, "name": p.name, "sequence": p.sequence, "pattern": p.pattern, "priority": p.priority,
            "matches": len(p.matches) if p.status == "Completed" else None, "match_positions": p.matches if p.status == "Completed" else [],
            "estimated_time": p.estimated_time, "status": p.status}

@app.get("/")
def home(): return send_from_directory(app.static_folder, "index.html")

@app.get("/api/state")
def state():
    return jsonify({"machines": [{"id":m.id,"name":m.name,"capacity":m.capacity,"queue":m.ready_queue} for m in machines], "processes": [process_dict(p) for p in processes]})

@app.post("/api/machines")
def add_machine():
    global next_machine_id
    data = request.get_json() or {}
    try:
        machine = Machine(next_machine_id, str(data["name"]).strip(), int(data["capacity"]))
        if not machine.name or machine.capacity < 1: raise ValueError
    except (KeyError, TypeError, ValueError): return jsonify(error="Name and positive capacity are required"), 400
    next_machine_id += 1; machines.append(machine); save_machine(machine)
    return jsonify({"id":machine.id,"name":machine.name,"capacity":machine.capacity,"queue":[]}), 201

@app.delete("/api/machines/<int:machine_id>")
def delete_machine(machine_id):
    global machines
    if not any(machine.id == machine_id for machine in machines):
        return jsonify(error="Virtual machine not found"), 404
    machines = [machine for machine in machines if machine.id != machine_id]
    return jsonify(message="Virtual machine deleted")

@app.post("/api/processes")
def add_process():
    global next_process_id
    data = request.get_json() or {}
    try:
        sequence, pattern = str(data["sequence"]).replace(" ", "").upper(), str(data["pattern"]).upper()
        process = Process(next_process_id, str(data["name"]).strip(), sequence, pattern, int(data["priority"]))
        if not process.name or not sequence or not pattern or process.priority < 1: raise ValueError
    except (KeyError, TypeError, ValueError): return jsonify(error="Provide valid process fields"), 400
    next_process_id += 1; processes.append(process); save_process(process)
    return jsonify(process_dict(process)), 201

def run(algorithm, calculate_positions=True):
    try: allocations, machine_data = simulate(machines, processes, algorithm, calculate_positions)
    except ValueError as error: return {"error": str(error)}, 400
    metrics = calculate(allocations, machine_data)
    for process in processes: save_process(process)
    saved = save_run(algorithm, metrics, allocations)
    return {"algorithm": algorithm, "allocations": allocations, "machines": machine_data, "processes": [process_dict(p) for p in processes], "metrics": metrics, "storage": "MySQL" if saved else "memory"}, 200

@app.post("/api/simulate")
def simulation():
    algorithm = (request.get_json() or {}).get("algorithm", "FCFS").upper()
    if algorithm not in {"FCFS", "SJF", "PRIORITY"}: return jsonify(error="Unknown algorithm"), 400
    result, status = run(algorithm); return jsonify(result), status

@app.post("/api/compare")
def compare():
    if not processes: return jsonify(error="Add at least one process"), 400
    results = {}
    for algorithm in ("FCFS", "SJF", "PRIORITY"):
        result, status = run(algorithm, calculate_positions=False)
        if status != 200: return jsonify(result), status
        results[algorithm] = result["metrics"]
    return jsonify(results)

if __name__ == "__main__": app.run(debug=True)
