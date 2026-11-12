from dataclasses import dataclass, field


@dataclass
class Machine:
    id: int
    name: str
    capacity: int
    ready_queue: list[int] = field(default_factory=list)
    busy_until: float = 0.0


@dataclass
class Process:
    id: int
    name: str
    sequence: str
    pattern: str
    priority: float
    work_units: int
    matches: list[int] = field(default_factory=list)
    patterns: list[dict[str, str]] = field(default_factory=list)
    signature_matches: list[list[int]] = field(default_factory=list)
    sequence_filename: str | None = None
    sequence_size: int | None = None
    pattern_filename: str | None = None
    pattern_size: int | None = None
    allocated_vm: str | None = None
    estimated_time: float | None = None
    status: str = "Queued"
