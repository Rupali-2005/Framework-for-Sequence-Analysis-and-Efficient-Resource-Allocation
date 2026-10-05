from models import Machine,Process
#Sort processes according to the selected scheduling algorithm
def ordered(procs:list[Process],algo:str)->list[Process]:
    if algo=="SJF":
        return sorted(procs,key=lambda p:(p.work_units,p.id))

    if algo=="PRIORITY":
        return sorted(procs,key=lambda p:(p.priority,p.id))
    #Default is FCFS
    return sorted(procs,key=lambda p:p.id)

#Run the scheduling simulation and assign processes to machines
def simulate(machines:list[Machine],procs:list[Process],algo:str)->tuple[list[dict],list[dict]]:
    if not machines:
        raise ValueError("Add at least one virtual machine")
    for mach in machines:
        mach.ready_queue,mach.busy_until=[],0.0
    allocs=[]
    for proc in ordered(procs,algo):
        #Pick the machine that should finish this process earliest
        mach=min(
            machines,
            key=lambda m:(m.busy_until+proc.work_units/m.capacity,m.id)
        )
        dur=round(proc.work_units/mach.capacity,2)
        start=mach.busy_until
        finish=round(start+dur,2)
        proc.estimated_time,proc.status=dur,"Completed"
        mach.ready_queue.append(proc.id)
        mach.busy_until=finish
        allocs.append({
            "process_id":proc.id,
            "machine_id":mach.id,
            "machine":mach.name,
            "start":start,
            "finish":finish,
            "waiting_time":start,
            "turnaround_time":finish,
            "estimated_time":dur
        })
    #Convert machine objects into data the API can return
    mach_data=[
        {
            "id":m.id,
            "name":m.name,
            "capacity":m.capacity,
            "ready_queue":m.ready_queue,
            "busy_until":m.busy_until
        }
        for m in machines
    ]
    return allocs,mach_data