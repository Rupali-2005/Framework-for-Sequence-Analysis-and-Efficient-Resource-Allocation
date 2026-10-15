"""MySQL persistence for machines, processes, runs, and allocations."""

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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS processes (
                id INT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                sequence_data MEDIUMTEXT NOT NULL,
                pattern_text VARCHAR(255) NOT NULL,
                priority INT NOT NULL,
                work_units INT NOT NULL,
                match_count INT NOT NULL DEFAULT 0,
                match_positions MEDIUMTEXT NOT NULL,
                estimated_time DECIMAL(10, 2) NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'Queued',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        _ensure_process_columns(cursor, db)

        cursor.execute("SELECT id, name, capacity FROM machines ORDER BY id")
        machines = [
            Machine(id=row[0], name=row[1], capacity=row[2])
            for row in cursor.fetchall()
        ]
        cursor.execute(
            """
            SELECT id, name, sequence_data, pattern_text, priority,
                   work_units, match_positions, estimated_time, status
            FROM processes
            ORDER BY id
            """
        )
        processes = [
            Process(
                id=row[0],
                name=row[1],
                sequence=row[2],
                pattern=row[3],
                priority=row[4],
                work_units=row[5],
                matches=json.loads(row[6]),
                estimated_time=float(row[7]) if row[7] is not None else None,
                status="Queued" if row[8] == "Processing" else row[8],
            )
            for row in cursor.fetchall()
        ]
        for process in processes:
            if process.status == "Queued":
                process.matches = []
                process.estimated_time = _estimate(process.sequence, machines)
                _save_process(cursor, process)

        db.commit()
        return machines, processes
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


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


def _estimate(sequence: str, machines: list[Machine]) -> float | None:
    if not machines:
        return None
    return round(len(sequence) / max(machine.capacity for machine in machines), 2)


def _save_process(cursor, process: Process) -> None:
    cursor.execute(
        """
        INSERT INTO processes (
            id, name, sequence_data, pattern_text, priority, work_units,
            match_count, match_positions, estimated_time, status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            name = VALUES(name),
            sequence_data = VALUES(sequence_data),
            pattern_text = VALUES(pattern_text),
            priority = VALUES(priority),
            work_units = VALUES(work_units),
            match_count = VALUES(match_count),
            match_positions = VALUES(match_positions),
            estimated_time = VALUES(estimated_time),
            status = VALUES(status)
        """,
        (
            process.id,
            process.name,
            process.sequence,
            process.pattern,
            process.priority,
            process.work_units,
            len(process.matches),
            json.dumps(process.matches),
            process.estimated_time,
            process.status,
        ),
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
    db = connection(_database_name())
    try:
        cursor = db.cursor()
        _save_process(cursor, process)
        db.commit()
        cursor.close()
    except Exception:
        db.rollback()
        raise
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
