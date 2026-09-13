"""Small optional MySQL persistence layer. The simulator still works without MySQL."""
import os
import mysql.connector


def connection():
    try:
        return mysql.connector.connect(host=os.getenv("MYSQL_HOST", "127.0.0.1"), port=int(os.getenv("MYSQL_PORT", "3306")),
            user=os.getenv("MYSQL_USER", "root"), password=os.getenv("MYSQL_PASSWORD", ""), database=os.getenv("MYSQL_DATABASE", "fesara"))
    except mysql.connector.Error:
        return None


def execute(query, values):
    db = connection()
    if not db: return False
    cursor = db.cursor(); cursor.execute(query, values); db.commit(); cursor.close(); db.close(); return True


def save_machine(machine):
    return execute("INSERT INTO machines (id,name,capacity) VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE name=VALUES(name),capacity=VALUES(capacity)", (machine.id, machine.name, machine.capacity))


def save_process(process):
    return execute("INSERT INTO processes (id,name,sequence_data,pattern_text,priority,work_units,match_count,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE status=VALUES(status),match_count=VALUES(match_count)", (process.id,process.name,process.sequence,process.pattern,process.priority,len(process.sequence),len(process.matches),process.status))


def save_run(algorithm, metrics, allocations):
    db = connection()
    if not db: return False
    cursor = db.cursor()
    cursor.execute("INSERT INTO simulation_runs (algorithm,average_waiting_time,average_turnaround_time,makespan) VALUES (%s,%s,%s,%s)", (algorithm,metrics["average_waiting_time"],metrics["average_turnaround_time"],metrics["makespan"]))
    run_id = cursor.lastrowid
    cursor.executemany("INSERT INTO allocations (run_id,process_id,machine_id,start_time,finish_time) VALUES (%s,%s,%s,%s,%s)", [(run_id,a["process_id"],a["machine_id"],a["start"],a["finish"]) for a in allocations])
    db.commit(); cursor.close(); db.close(); return True
