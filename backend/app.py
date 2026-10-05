import os
from flask import Flask,jsonify,request,send_from_directory
from dotenv import load_dotenv
from kmp import find_all
from models import Machine,Process
from scheduling import simulate
from metrics import calculate

load_dotenv()
app=Flask(__name__,static_folder="../frontend",static_url_path="")
machines:list[Machine]=[]
procs:list[Process]=[]
next_mach_id=next_proc_id=1

def process_dict(p):
    # Keep the response format in one place
    return {
        "id":p.id,
        "name":p.name,
        "sequence":p.sequence,
        "pattern":p.pattern,
        "priority":p.priority,
        "work_units":p.work_units,
        "matches":len(p.matches),
        "match_positions":p.matches,
        "estimated_time":p.estimated_time,
        "status":p.status
    }

@app.route("/")
def home():
    return send_from_directory(app.static_folder,"index.html")

@app.route("/api/state")
def state():
    return jsonify({
        "machines":[
            {
                "id":m.id,
                "name":m.name,
                "capacity":m.capacity,
                "queue":m.ready_queue
            }
            for m in machines
        ],
        "processes":[process_dict(p) for p in procs]
    })

@app.route("/api/machines",methods=["POST"])
def add_machine():
    global next_mach_id
    data=request.get_json() or {}
    try:
        mach=Machine(
            next_mach_id,
            str(data["name"]).strip(),
            int(data["capacity"])
        )
        if not mach.name or mach.capacity<1:
            raise ValueError
    except (KeyError,TypeError,ValueError):
        return jsonify(error="Name and positive capacity are required"),400
    next_mach_id+=1
    machines.append(mach)
    return jsonify({
        "id":mach.id,
        "name":mach.name,
        "capacity":mach.capacity,
        "queue":[]
    }),201

@app.route("/api/processes",methods=["POST"])
def add_process():
    global next_proc_id
    data=request.get_json() or {}
    try:
        seq=str(data["sequence"]).replace(" ","").upper()
        pat=str(data["pattern"]).upper()
        proc=Process(
            next_proc_id,
            str(data["name"]).strip(),
            seq,
            pat,
            int(data["priority"]),
            int(data["work_units"])
        )
        if not proc.name or not seq or not pat:
            raise ValueError
        if proc.priority<1 or proc.work_units<1:
            raise ValueError
    except (KeyError,TypeError,ValueError):
        return jsonify(error="Provide valid process fields"),400

    # Find all matches before saving the process
    proc.matches=find_all(proc.sequence,proc.pattern)
    next_proc_id+=1
    procs.append(proc)
    return jsonify(process_dict(proc)),201

def run(algo):
    try:
        allocs,mach_data=simulate(machines,procs,algo)
    except ValueError as err:
        return {"error":str(err)},400

    # Metrics are calculated after scheduling finishes
    return {
        "algorithm":algo,
        "allocations":allocs,
        "machines":mach_data,
        "processes":[process_dict(p) for p in procs],
        "metrics":calculate(allocs,mach_data)
    },200

@app.route("/api/simulate",methods=["POST"])
def simulation():
    algo=(request.get_json() or {}).get("algorithm","FCFS").upper()
    if algo not in {"FCFS","SJF","PRIORITY"}:
        return jsonify(error="Unknown algorithm"),400
    res,status=run(algo)
    return jsonify(res),status

@app.route("/api/compare",methods=["POST"])
def compare():
    if not procs:
        return jsonify(error="Add at least one process"),400

    results={}
    # Run each algorithm for a quick comparison
    for algo in ("FCFS","SJF","PRIORITY"):
        res,status=run(algo)
        if status!=200:
            return jsonify(res),status
        results[algo]=res["metrics"]

    return jsonify(results)

if __name__=="__main__":
    app.run(debug=True)
