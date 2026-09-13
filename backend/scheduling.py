"""Deterministic scheduling and least-finish-time machine allocation."""
from math import ceil
from kmp import find_all_by_capacity
from models import Machine, Process


def ordered(processes: list[Process], algorithm: str) -> list[Process]:
    if algorithm == "SJF":
        return sorted(processes, key=lambda p: (len(p.sequence), p.id))
    if algorithm == "PRIORITY":
        return sorted(processes, key=lambda p: (p.priority, p.id))
    return sorted(processes, key=lambda p: p.id)  # FCFS


def simulate(machines: list[Machine], processes: list[Process], algorithm: str, calculate_positions: bool = True) -> tuple[list[dict], list[dict]]:
    if not machines:
        raise ValueError("Add at least one virtual machine")
    for machine in machines:
        machine.ready_queue, machine.busy_until = [], 0.0
    allocations = []
    for process in ordered(processes, algorithm):
        # Lowest projected completion time; machine ID is a stable tie-breaker.
        machine = min(machines, key=lambda m: (m.busy_until + ceil(len(process.sequence) / m.capacity), m.id))
        duration = ceil(len(process.sequence) / machine.capacity)
        start, finish = machine.busy_until, round(machine.busy_until + duration, 2)
        if calculate_positions:
            process.matches = find_all_by_capacity(process.sequence, process.pattern, machine.capacity)
        process.estimated_time, process.status = duration, "Completed"
        machine.ready_queue.append(process.id)
        machine.busy_until = finish
        allocations.append({"process_id": process.id, "machine_id": machine.id, "machine": machine.name,
                            "start": start, "finish": finish, "waiting_time": start,
                            "turnaround_time": finish, "estimated_time": duration})
    machine_data = [{"id": m.id, "name": m.name, "capacity": m.capacity,
                     "ready_queue": m.ready_queue, "busy_until": m.busy_until} for m in machines]
    return allocations, machine_data
