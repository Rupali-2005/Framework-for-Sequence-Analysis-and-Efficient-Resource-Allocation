from dataclasses import dataclass, field


@dataclass
class Machine:
    id: int
    name: str
    capacity: int  # work units per simulated second
    ready_queue: list[int] = field(default_factory=list)
    busy_until: float = 0.0


@dataclass
class Process:
    id: int
    name: str
    sequence: str
    pattern: str
    priority: int
    work_units: int
    matches: list[int] = field(default_factory=list)
    estimated_time: float = 0.0
    status: str = "Queued"
