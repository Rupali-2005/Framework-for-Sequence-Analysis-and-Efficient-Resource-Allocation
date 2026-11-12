"""MySQL persistence for machines, processes, uploaded-file records, and runs."""

import json
import os
import re

import mysql.connector

from models import Machine, Process


def _database_name() -> str:
    name = os.getenv("MYSQL_DATABASE") or "PBL"
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise ValueError("MYSQL_DATABASE may contain only letters, digits, and underscores")
    return name


def connection(database: str | None = None):
    options = {
        "host": os.getenv("MYSQL_HOST") or "127.0.0.1",
        "port": int(os.getenv("MYSQL_PORT") or "3306"),
        "user": os.getenv("MYSQL_USER") or "root",
        "password": os.getenv("MYSQL_PASSWORD") or "",
    }
    if database:
        options["database"] = database
    return mysql.connector.connect(**options)


def initialize() -> tuple[list[Machine], list[Process]]:
    database = _database_name()
    server = connection()
    try:
        cursor = server.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{database}`")
        cursor.close()
        server.commit()
    finally:
        server.close()

    db = connection(database)
    try:
        cursor = db.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS machines (
                id INT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                capacity INT NOT NULL,
                is_active TINYINT(1) NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS processes (
                id INT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                sequence_data MEDIUMTEXT NULL,
                pattern_text VARCHAR(255) NULL,
                priority DECIMAL(6, 2) NOT NULL,
                work_units BIGINT NOT NULL,
                match_count INT NOT NULL DEFAULT 0,
                match_positions MEDIUMTEXT NOT NULL,
                estimated_time DECIMAL(10, 2) NULL,
                signature_results MEDIUMTEXT NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'Queued',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS file_records (
                id INT AUTO_INCREMENT PRIMARY KEY,
                process_id INT NOT NULL,
                kind VARCHAR(20) NOT NULL,
                filename VARCHAR(255) NOT NULL,
                size_bytes BIGINT UNSIGNED NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY process_file_kind (process_id, kind),
                FOREIGN KEY (process_id) REFERENCES processes(id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS simulation_runs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                algorithm VARCHAR(20) NOT NULL,
                average_waiting_time DECIMAL(10, 2) NOT NULL,
                average_turnaround_time DECIMAL(10, 2) NOT NULL,
                makespan DECIMAL(10, 2) NOT NULL,
                executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS allocations (
                id INT AUTO_INCREMENT PRIMARY KEY,
                run_id INT NOT NULL,
                process_id INT NOT NULL,
                machine_id INT NOT NULL,
                start_time DECIMAL(10, 2) NOT NULL,
                finish_time DECIMAL(10, 2) NOT NULL,
                FOREIGN KEY (run_id) REFERENCES simulation_runs(id),
                FOREIGN KEY (process_id) REFERENCES processes(id),
                FOREIGN KEY (machine_id) REFERENCES machines(id)
            )
            """
        )
        _ensure_machine_columns(cursor)
        _ensure_process_columns(cursor, db)
        _clear_process_content(cursor)

        machines, processes = _load_state(cursor, recover_processing=True)

        db.commit()
        return machines, processes
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def load_state() -> tuple[list[Machine], list[Process]]:
    db = connection(_database_name())
    try:
        cursor = db.cursor()
        machines, processes = _load_state(cursor)
        cursor.close()
        return machines, processes
    finally:
        db.close()


def next_process_id() -> int:
    db = connection(_database_name())
    try:
        cursor = db.cursor()
        cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM processes")
        return cursor.fetchone()[0]
    finally:
        db.close()


def next_machine_id() -> int:
    db = connection(_database_name())
    try:
        cursor = db.cursor()
        cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM machines")
        return cursor.fetchone()[0]
    finally:
        db.close()


def _load_state(
    cursor,
    recover_processing: bool = False,
) -> tuple[list[Machine], list[Process]]:
    cursor.execute(
        "SELECT id, name, capacity FROM machines "
        "WHERE is_active = 1 ORDER BY id"
    )
    machines = [
        Machine(id=row[0], name=row[1], capacity=row[2])
        for row in cursor.fetchall()
    ]
    cursor.execute(
        """
        SELECT id, name, sequence_data, pattern_text, priority,
               work_units, match_positions, estimated_time, status
        FROM processes
        WHERE sequence_data IS NOT NULL AND pattern_text IS NOT NULL
        ORDER BY id
        """
    )
    processes = [
        Process(
            id=row[0],
            name=row[1],
            sequence=row[2],
            pattern=row[3],
            priority=float(row[4]),
            work_units=row[5],
            matches=json.loads(row[6]),
            estimated_time=float(row[7]) if row[7] is not None else None,
            status="Queued" if recover_processing and row[8] == "Processing" else row[8],
        )
        for row in cursor.fetchall()
    ]
    if recover_processing:
        for process in processes:
            if process.status == "Queued":
                process.matches = []
                process.estimated_time = _estimate(process.sequence, machines)
                _save_process(cursor, process)
    return machines, processes


def _ensure_process_columns(cursor, db) -> None:
    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'processes'
        """
    )
    columns = {row[0] for row in cursor.fetchall()}

    if "match_positions" not in columns:
        cursor.execute(
            "ALTER TABLE processes ADD COLUMN match_positions MEDIUMTEXT NULL"
        )
        cursor.execute(
            "UPDATE processes SET match_positions = '[]' WHERE match_positions IS NULL"
        )
        cursor.execute(
            "ALTER TABLE processes MODIFY match_positions MEDIUMTEXT NOT NULL"
        )
    if "estimated_time" not in columns:
        cursor.execute(
            "ALTER TABLE processes ADD COLUMN estimated_time DECIMAL(10, 2) NULL"
        )
    if "signature_results" not in columns:
        cursor.execute(
            "ALTER TABLE processes ADD COLUMN signature_results MEDIUMTEXT NULL"
        )
        cursor.execute(
            "UPDATE processes SET signature_results = '[]' "
            "WHERE signature_results IS NULL"
        )
        cursor.execute(
            "ALTER TABLE processes MODIFY signature_results MEDIUMTEXT NOT NULL"
        )
    cursor.execute(
        """
        SELECT DATA_TYPE
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'processes'
          AND COLUMN_NAME = 'work_units'
        """
    )
    row = cursor.fetchone()
    if row and row[0].lower() != "bigint":
        cursor.execute(
            "ALTER TABLE processes MODIFY work_units BIGINT NOT NULL"
        )
    _ensure_priority_precision(cursor)


def _ensure_machine_columns(cursor) -> None:
    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'machines'
        """
    )
    columns = {row[0] for row in cursor.fetchall()}
    if "is_active" not in columns:
        cursor.execute(
            "ALTER TABLE machines ADD COLUMN is_active "
            "TINYINT(1) NOT NULL DEFAULT 1"
        )


def _ensure_priority_precision(cursor) -> None:
    cursor.execute(
        """
        SELECT DATA_TYPE
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'processes'
          AND COLUMN_NAME = 'priority'
        """
    )
    row = cursor.fetchone()
    if row and row[0].lower() not in {"decimal", "numeric", "float", "double"}:
        cursor.execute(
            "ALTER TABLE processes MODIFY priority DECIMAL(6, 2) NOT NULL"
        )


def _clear_process_content(cursor) -> None:
    cursor.execute(
        """
        SELECT COLUMN_NAME, IS_NULLABLE
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'processes'
          AND COLUMN_NAME IN ('sequence_data', 'pattern_text')
        """
    )
    nullable = {row[0]: row[1] == "YES" for row in cursor.fetchall()}
    if nullable.get("sequence_data") is False:
        cursor.execute(
            "ALTER TABLE processes MODIFY sequence_data MEDIUMTEXT NULL"
        )
    if nullable.get("pattern_text") is False:
        cursor.execute(
            "ALTER TABLE processes MODIFY pattern_text VARCHAR(255) NULL"
        )
    cursor.execute(
        "UPDATE processes SET sequence_data = NULL, pattern_text = NULL"
    )


def _estimate(sequence: str, machines: list[Machine]) -> float | None:
    if not machines:
        return None
    return round(len(sequence) / max(machine.capacity for machine in machines), 2)


def _save_process(cursor, process: Process) -> None:
    signatures = process.patterns or [
        {"name": process.pattern, "pattern": process.pattern}
    ]
    signature_results = [
        {
            "name": signature["name"],
            "match_count": len(process.signature_matches[index])
            if process.status == "Completed"
            and index < len(process.signature_matches)
            else 0,
            "match_positions": process.signature_matches[index]
            if process.status == "Completed"
            and index < len(process.signature_matches)
            else [],
        }
        for index, signature in enumerate(signatures)
    ]
    cursor.execute(
        """
        INSERT INTO processes (
            id, name, sequence_data, pattern_text, priority, work_units,
            match_count, match_positions, estimated_time, signature_results,
            status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            name = VALUES(name),
            sequence_data = VALUES(sequence_data),
            pattern_text = VALUES(pattern_text),
            priority = VALUES(priority),
            work_units = VALUES(work_units),
            match_count = VALUES(match_count),
            match_positions = VALUES(match_positions),
            estimated_time = VALUES(estimated_time),
            signature_results = VALUES(signature_results),
            status = VALUES(status)
        """,
        (
            process.id,
            process.name,
            None,
            None,
            process.priority,
            process.work_units,
            len(process.matches),
            json.dumps(process.matches),
            process.estimated_time,
            json.dumps(signature_results),
            process.status,
        ),
    )


def _save_file_records(cursor, process: Process) -> None:
    records = (
        ("sequence", process.sequence_filename, process.sequence_size),
        ("pattern", process.pattern_filename, process.pattern_size),
    )
    for kind, filename, size_bytes in records:
        if filename is None or size_bytes is None:
            continue
        cursor.execute(
            """
            INSERT INTO file_records (process_id, kind, filename, size_bytes)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                filename = VALUES(filename),
                size_bytes = VALUES(size_bytes)
            """,
            (process.id, kind, filename, size_bytes),
        )


def _execute_write(query: str, values: tuple) -> None:
    db = connection(_database_name())
    try:
        cursor = db.cursor()
        cursor.execute(query, values)
        db.commit()
        cursor.close()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def save_machine(machine: Machine) -> None:
    _execute_write(
        """
        INSERT INTO machines (id, name, capacity)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
            name = VALUES(name),
            capacity = VALUES(capacity)
        """,
        (machine.id, machine.name, machine.capacity),
    )


def save_process(process: Process) -> None:
    save_processes([process])


def save_processes(processes: list[Process]) -> None:
    db = connection(_database_name())
    try:
        cursor = db.cursor()
        for process in processes:
            _save_process(cursor, process)
            _save_file_records(cursor, process)
        db.commit()
        cursor.close()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def delete_machine(machine_id: int) -> None:
    _execute_write(
        "UPDATE machines SET is_active = 0 WHERE id = %s",
        (machine_id,),
    )


def load_dataset() -> list[dict]:
    db = connection(_database_name())
    try:
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT p.id, p.name, p.priority, p.work_units, p.match_count,
                   p.match_positions, p.signature_results, p.estimated_time,
                   p.status, sequence_file.filename, sequence_file.size_bytes,
                   pattern_file.filename, pattern_file.size_bytes
            FROM processes AS p
            LEFT JOIN file_records AS sequence_file
              ON sequence_file.process_id = p.id
             AND sequence_file.kind = 'sequence'
            LEFT JOIN file_records AS pattern_file
              ON pattern_file.process_id = p.id
             AND pattern_file.kind = 'pattern'
            ORDER BY p.id
            """
        )
        return [
            {
                "id": row[0],
                "name": row[1],
                "priority": float(row[2]),
                "work_units": row[3],
                "matches": row[4] if row[8] == "Completed" else None,
                "match_positions": json.loads(row[5]),
                "signature_results": json.loads(row[6]),
                "estimated_time": (
                    float(row[7]) if row[7] is not None else None
                ),
                "status": row[8],
                "sequence_filename": row[9],
                "sequence_size": row[10],
                "pattern_filename": row[11],
                "pattern_size": row[12],
                "content_available": False,
            }
            for row in cursor.fetchall()
        ]
    finally:
        db.close()


def save_run(algorithm: str, metrics: dict, allocations: list[dict]) -> int:
    db = connection(_database_name())
    try:
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO simulation_runs (
                algorithm, average_waiting_time,
                average_turnaround_time, makespan
            )
            VALUES (%s, %s, %s, %s)
            """,
            (
                algorithm,
                metrics["average_waiting_time"],
                metrics["average_turnaround_time"],
                metrics["makespan"],
            ),
        )
        run_id = cursor.lastrowid
        cursor.executemany(
            """
            INSERT INTO allocations (
                run_id, process_id, machine_id, start_time, finish_time
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            [
                (
                    run_id,
                    allocation["process_id"],
                    allocation["machine_id"],
                    allocation["start"],
                    allocation["finish"],
                )
                for allocation in allocations
            ],
        )
        db.commit()
        cursor.close()
        return run_id
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
