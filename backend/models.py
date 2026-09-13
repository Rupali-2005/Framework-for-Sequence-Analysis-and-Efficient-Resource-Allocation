from dataclasses import dataclass, field


@dataclass
class Machine:
    id: int
    name: str
    capacity: int  # characters scanned per simulated second
    ready_queue: list[int] = field(default_factory=list)
    busy_until: float = 0.0


@dataclass
class Process:
    id: int
    name: str
    sequence: str
    pattern: str
    priority: int
    matches: list[int] = field(default_factory=list)
    processing_time: float = 0.0
    status: str = "Queued"
