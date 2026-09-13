def calculate(allocations: list[dict], machines: list[dict]) -> dict:
    if not allocations:
        return {"average_waiting_time": 0, "average_turnaround_time": 0, "makespan": 0, "machine_utilization": {}}
    makespan = max(item["finish"] for item in allocations)
    utilization = {}
    for machine in machines:
        busy = sum(item["estimated_time"] for item in allocations if item["machine_id"] == machine["id"])
        utilization[machine["name"]] = round((busy / makespan * 100) if makespan else 0, 2)
    return {"average_waiting_time": round(sum(a["waiting_time"] for a in allocations) / len(allocations), 2),
            "average_turnaround_time": round(sum(a["turnaround_time"] for a in allocations) / len(allocations), 2),
            "makespan": makespan, "machine_utilization": utilization}
