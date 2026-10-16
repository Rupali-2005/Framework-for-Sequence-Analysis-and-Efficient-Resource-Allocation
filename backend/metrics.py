def calculate(allocations:list[dict], machines:list[dict]) -> dict:
    if not allocations:
        return {
            "average_waiting_time":0,
            "average_turnaround_time":0,
            "makespan":0, #Makespan is the total  time from the start of the first job  to the completion of the last job 
            "throughput":0,
            "machine_utilization":{},
        }

    makespan=max(allocation["finish"] for allocation in allocations)
    allocation_count=len(allocations)
    utilization={}

    for machine in machines:
        busy_time=sum(allocation["estimated_time"] for allocation in allocations if allocation["machine_id"] == machine["id"] )
        utilization[machine["name"]]=round(busy_time / makespan * 100 if makespan else 0,2, )

    waiting_time=sum(allocation["turnaround_time"] - allocation["estimated_time"] for allocation in allocations )
    turnaround_time=sum(allocation["turnaround_time"] for allocation in allocations)

    return {
        "average_waiting_time":round(waiting_time / allocation_count, 2),
        "average_turnaround_time":round(turnaround_time / allocation_count,2,),
        "makespan":round(makespan, 2),
        "throughput":round(allocation_count / makespan, 2) if makespan else 0,
        "machine_utilization":utilization,
    }
