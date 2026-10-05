def calculate(allocs:list[dict],machines:list[dict])->dict:
    if not allocs:
        # Nothing to calculate yet
        return {
            "average_waiting_time":0,
            "average_turnaround_time":0,
            "makespan":0,
            "machine_utilization":{}
        }
    makespan=max(item["finish"] for item in allocs)
    util={}
    for mach in machines:
        # Add up the time this machine was actually working
        busy=sum(
            item["estimated_time"]
            for item in allocs
            if item["machine_id"]==mach["id"]
        )
        util[mach["name"]]=round(
            (busy/makespan*100) if makespan else 0,2
        )
    return {
        "average_waiting_time":round(sum(a["waiting_time"] for a in allocs)/len(allocs),2),
        "average_turnaround_time":round(sum(a["turnaround_time"] for a in allocs)/len(allocs),2),
        "makespan":makespan,
        "machine_utilization":util
    }
