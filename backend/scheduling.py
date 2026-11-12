from math import isfinite

from models import Machine, Process


SUPPORTED_ALGORITHMS = {"FCFS", "SJF", "PRIORITY", "RR", "SRTF"}


def ordered(processes: list[Process], algorithm: str) -> list[Process]:
    if algorithm in {"SJF", "SRTF"}:
        return sorted(processes, key=lambda process: (process.work_units, process.id))

    if algorithm == "PRIORITY":
        return sorted(processes, key=lambda process: (process.priority, process.id))

    return sorted(processes, key=lambda process: process.id)


def _machine_data(machines: list[Machine]) -> list[dict]:
    return [
        {
            "id": machine.id,
            "name": machine.name,
            "capacity": machine.capacity,
            "ready_queue": machine.ready_queue,
            "busy_until": machine.busy_until,
        }
        for machine in machines
    ]


def _allocation(
    process: Process,
    machine: Machine,
    start: float,
    finish: float,
) -> dict:
    duration = round(process.work_units / machine.capacity, 2)
    process.estimated_time = round(
        len(process.sequence) / machine.capacity,
        2,
    )
    machine.ready_queue.append(process.id)

    return {
        "process_id": process.id,
        "machine_id": machine.id,
        "machine": machine.name,
        "start": round(start, 2),
        "finish": round(finish, 2),
        "waiting_time": round(finish - duration, 2),
        "turnaround_time": round(finish, 2),
        "estimated_time": duration,
    }


def _schedule_queue(
    machine: Machine,
    processes: list[Process],
    algorithm: str,
    time_quantum: float,
) -> list[dict]:
    if algorithm == "SRTF":
        processes = sorted(
            processes,
            key=lambda process: (
                process.work_units / machine.capacity,
                process.id,
            ),
        )

    if algorithm != "RR":
        allocations = []
        current_time = 0.0

        for process in processes:
            duration = process.work_units / machine.capacity
            finish = current_time + duration
            allocations.append(
                _allocation(process, machine, current_time, finish)
            )
            current_time = finish

        machine.busy_until = round(current_time, 2)
        return allocations

    remaining = {
        process.id: process.work_units / machine.capacity
        for process in processes
    }
    first_start = {}
    finish_times = {}
    current_time = 0.0
    ready = list(processes)

    while ready:
        process = ready.pop(0)
        first_start.setdefault(process.id, current_time)
        slice_duration = min(time_quantum, remaining[process.id])
        current_time += slice_duration
        remaining[process.id] -= slice_duration

        if remaining[process.id] <= 1e-9:
            finish_times[process.id] = current_time
        else:
            ready.append(process)

    allocations = []
    for process in processes:
        allocations.append(
            _allocation(
                process,
                machine,
                first_start[process.id],
                finish_times[process.id],
            )
        )

    machine.busy_until = round(current_time, 2)
    return allocations


def simulate(
    machines: list[Machine],
    processes: list[Process],
    algorithm: str,
    time_quantum: float = 2.0,
) -> tuple[list[dict], list[dict]]:
    if not machines:
        raise ValueError("Add at least one virtual machine")
    if algorithm not in SUPPORTED_ALGORITHMS:
        raise ValueError("Unknown algorithm")
    if algorithm == "RR" and (
        not isfinite(time_quantum) or time_quantum <= 0
    ):
        raise ValueError("Time quantum must be greater than zero")

    for machine in machines:
        machine.ready_queue = []
        machine.busy_until = 0.0

    machine_queues: dict[int, list[Process]] = {
        machine.id: [] for machine in machines
    }

    for process in ordered(processes, algorithm):
        machine = min(
            machines,
            key=lambda item: (
                item.busy_until + process.work_units / item.capacity,
                item.id,
            ),
        )
        machine_queues[machine.id].append(process)
        machine.busy_until += process.work_units / machine.capacity

    allocations = []
    for machine in machines:
        machine.busy_until = 0.0
        allocations.extend(
            _schedule_queue(
                machine,
                machine_queues[machine.id],
                algorithm,
                time_quantum,
            )
        )

    return allocations, _machine_data(machines)
