import json
import unittest
from io import BytesIO
from pathlib import Path
from threading import Event, Lock
from unittest.mock import patch

import app as app_module
from charts import dashboard_chart
from kmp import find_all
from metrics import calculate
from models import Machine, Process
from scheduling import simulate
import storage
from app import app as flask_app, estimate_time
from app import machines as live_machines
from app import processes as live_processes


def make_process(process_id: int, work_units: int) -> Process:
    return Process(
        id=process_id,
        name=f"Process {process_id}",
        sequence="ATGC",
        pattern="AT",
        priority=1,
        work_units=work_units,
    )


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.previous_storage_initialized = app_module.storage_initialized
        self.previous_login_accounts = app_module.LOGIN_ACCOUNTS
        app_module.storage_initialized = True
        app_module.LOGIN_ACCOUNTS = {
            "professor": {"username": "professor", "password": "professor-pass"},
            "management": {"username": "management", "password": "management-pass"},
            "student": {"username": "student", "password": "student-pass"},
        }
        self.client = flask_app.test_client()
        self.client.post(
            "/api/auth/login",
            json={"username": "student", "password": "student-pass"},
        )
        self.storage_patches = [
            patch("app.storage.save_machine"),
            patch("app.storage.save_process"),
            patch("app.storage.save_run", return_value=1),
        ]
        for storage_patch in self.storage_patches:
            storage_patch.start()

    def tearDown(self):
        for storage_patch in self.storage_patches:
            storage_patch.stop()
        app_module.LOGIN_ACCOUNTS = self.previous_login_accounts
        app_module.storage_initialized = self.previous_storage_initialized

    def test_kmp_finds_overlapping_matches(self):
        self.assertEqual(find_all("AAAA", "AA"), [0, 1, 2])

    def test_kmp_pauses_after_each_machine_capacity_of_comparisons(self):
        with patch("kmp.time.sleep") as sleep:
            matches = find_all("AAAA", "AA", comparison_capacity=2)

        self.assertEqual(matches, [0, 1, 2])
        self.assertEqual(sleep.call_count, 2)
        sleep.assert_called_with(1)

    def test_estimated_time_accounts_for_each_pattern(self):
        self.assertEqual(estimate_time("AAAA", 2, pattern_count=3), 6)

    def test_work_units_are_calculated_from_sequence_and_signature_count(self):
        process = app_module._build_process(
            {
                "name": "Multi-signature scan",
                "sequence": "ATGC",
                "pattern": "AT",
                "patterns": [
                    {"name": "First", "pattern": "AT"},
                    {"name": "Second", "pattern": "GC"},
                ],
                "priority": 1,
            },
            process_id=1,
            role="student",
        )

        self.assertEqual(process.work_units, 8)

    def test_sjf_schedules_shortest_process_first(self):
        machines = [Machine(1, "VM", 10)]
        processes = [make_process(1, 50), make_process(2, 10)]

        allocations, _ = simulate(machines, processes, "SJF")

        self.assertEqual(allocations[0]["process_id"], 2)

    def test_priority_scheduling_orders_fractional_effective_priorities(self):
        machines = [Machine(1, "VM", 10)]
        processes = [make_process(1, 10), make_process(2, 10)]
        processes[0].priority = 2.0
        processes[1].priority = 1.5

        allocations, _ = simulate(machines, processes, "PRIORITY")

        self.assertEqual(allocations[0]["process_id"], 2)

    def test_srtf_schedules_shortest_ready_process_first(self):
        machines = [Machine(1, "VM", 10)]
        processes = [make_process(1, 50), make_process(2, 10)]

        allocations, _ = simulate(machines, processes, "SRTF")

        self.assertEqual(allocations[0]["process_id"], 2)

    def test_round_robin_respects_time_quantum(self):
        machines = [Machine(1, "VM", 1)]
        processes = [make_process(1, 4), make_process(2, 2)]

        allocations, _ = simulate(machines, processes, "RR", time_quantum=1)
        finish_times = {
            allocation["process_id"]: allocation["finish"]
            for allocation in allocations
        }

        self.assertEqual(finish_times, {1: 6, 2: 4})
        self.assertEqual(allocations[0]["waiting_time"], 2)
        self.assertEqual(allocations[1]["waiting_time"], 2)

    def test_round_robin_rejects_non_positive_quantum(self):
        with self.assertRaisesRegex(ValueError, "Time quantum"):
            simulate([Machine(1, "VM", 1)], [], "RR", time_quantum=0)

    def test_metrics_include_waiting_turnaround_and_throughput(self):
        allocations = [
            {
                "process_id": 1,
                "machine_id": 1,
                "finish": 6,
                "turnaround_time": 6,
                "estimated_time": 4,
            },
            {
                "process_id": 2,
                "machine_id": 1,
                "finish": 4,
                "turnaround_time": 4,
                "estimated_time": 2,
            },
        ]

        result = calculate(allocations, [{"id": 1, "name": "VM"}])

        self.assertEqual(result["average_waiting_time"], 2)
        self.assertEqual(result["average_turnaround_time"], 5)
        self.assertEqual(result["makespan"], 6)
        self.assertEqual(result["throughput"], 0.33)
        self.assertEqual(result["machine_utilization"], {"VM": 100.0})

    def test_dashboard_chart_returns_embeddable_png(self):
        chart = dashboard_chart(
            {
                "FCFS": {
                    "average_waiting_time": 0,
                    "average_turnaround_time": 4,
                    "makespan": 4,
                    "machine_utilization": {"VM": 100},
                }
            }
        )

        self.assertTrue(chart.startswith("data:image/png;base64,"))
        self.assertGreater(len(chart), 1000)

    def test_compare_runs_all_algorithms_without_changing_live_state(self):
        previous_machines = live_machines[:]
        previous_processes = live_processes[:]
        live_machines[:] = [Machine(1, "VM", 1)]
        live_processes[:] = [make_process(1, 4), make_process(2, 2)]

        try:
            response = self.client.post(
                "/api/compare",
                json={"time_quantum": 1},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                set(response.json["results"]),
                {"FCFS", "SJF", "PRIORITY", "RR", "SRTF"},
            )
            self.assertTrue(response.json["chart"].startswith("data:image/png;base64,"))
            self.assertEqual(app_module.storage.save_run.call_count, 5)
            self.assertEqual(live_machines[0].ready_queue, [])
            self.assertTrue(
                all(process.status == "Queued" for process in live_processes)
            )
        finally:
            live_machines[:] = previous_machines
            live_processes[:] = previous_processes

    def test_single_simulation_does_not_return_a_chart(self):
        previous_machines = live_machines[:]
        previous_processes = live_processes[:]
        live_machines[:] = [Machine(1, "VM", 1)]
        live_processes[:] = [make_process(1, 4)]

        try:
            client = self.client
            with patch("kmp.time.sleep"):
                response = client.post(
                    "/api/simulate",
                    json={"algorithm": "FCFS"},
                )
                self.assertEqual(response.status_code, 202)
                self.assertNotIn("chart", response.json)
                self.assertEqual(response.json["status"], "running")
                for _ in range(100):
                    progress = client.get(
                        f"/api/simulation/{response.json['run_id']}"
                    )
                    if progress.json["status"] != "running":
                        break
                    Event().wait(0.01)

            self.assertEqual(progress.json["status"], "completed")
            self.assertEqual(app_module.storage.save_run.call_count, 1)
        finally:
            live_machines[:] = previous_machines
            live_processes[:] = previous_processes

    def test_simulation_matches_processes_concurrently_across_machines(self):
        previous_machines = live_machines[:]
        previous_processes = live_processes[:]
        live_machines[:] = [
            Machine(1, "VM 1", 2),
            Machine(2, "VM 2", 2),
        ]
        live_processes[:] = [make_process(1, 4), make_process(2, 4)]
        both_started = Event()
        release_matching = Event()
        calls_lock = Lock()
        sleep_calls = 0

        def wait_for_matching(_seconds: float) -> None:
            nonlocal sleep_calls
            with calls_lock:
                sleep_calls += 1
                if sleep_calls == 2:
                    both_started.set()
            release_matching.wait(timeout=2)

        try:
            with patch("kmp.time.sleep", side_effect=wait_for_matching):
                response = self.client.post(
                    "/api/simulate",
                    json={"algorithm": "FCFS"},
                )
                self.assertEqual(response.status_code, 202)

                try:
                    self.assertTrue(both_started.wait(timeout=2))
                    progress = self.client.get(
                        f"/api/simulation/{response.json['run_id']}"
                    )
                    self.assertEqual(
                        [
                            process["status"]
                            for process in progress.json["processes"]
                        ],
                        ["Processing", "Processing"],
                    )
                finally:
                    release_matching.set()

                for _ in range(100):
                    progress = self.client.get(
                        f"/api/simulation/{response.json['run_id']}"
                    )
                    if progress.json["status"] != "running":
                        break
                    Event().wait(0.01)

            self.assertEqual(progress.json["status"], "completed")
            self.assertEqual(
                [
                    process["matches"]
                    for process in progress.json["result"]["processes"]
                ],
                [1, 1],
            )
        finally:
            release_matching.set()
            live_machines[:] = previous_machines
            live_processes[:] = previous_processes

    def test_process_matches_only_when_simulation_starts(self):
        previous_machines = live_machines[:]
        previous_processes = live_processes[:]
        previous_next_process_id = app_module.next_process_id
        live_machines.clear()
        live_processes.clear()
        app_module.next_process_id = 1

        try:
            client = self.client
            machine_response = client.post(
                "/api/machines",
                json={"name": "VM", "capacity": 2},
            )
            self.assertEqual(machine_response.status_code, 201)

            with patch("app.find_all") as find_all_mock:
                process_response = client.post(
                    "/api/processes",
                    json={
                        "name": "Genome scan",
                        "sequence": "AAAA",
                        "pattern": "AA",
                        "priority": 1,
                    },
                )
                second_process_response = client.post(
                    "/api/processes",
                    json={
                        "name": "Second genome scan",
                        "sequence": "CCCC",
                        "pattern": "CC",
                        "priority": 1,
                        "work_units": 999,
                    },
                )

            self.assertEqual(process_response.status_code, 201)
            self.assertEqual(second_process_response.status_code, 201)
            self.assertEqual(process_response.json["work_units"], 4)
            self.assertEqual(second_process_response.json["work_units"], 4)
            self.assertIsNone(process_response.json["matches"])
            self.assertEqual(process_response.json["estimated_time"], 2)
            self.assertEqual(second_process_response.json["estimated_time"], 2)
            find_all_mock.assert_not_called()

            sleep_started = Event()
            release_sleep = Event()

            def wait_during_matching(_seconds: float) -> None:
                sleep_started.set()
                release_sleep.wait(timeout=2)

            with patch("kmp.time.sleep", side_effect=wait_during_matching) as sleep:
                simulation_response = client.post(
                    "/api/simulate",
                    json={"algorithm": "FCFS"},
                )
                self.assertEqual(simulation_response.status_code, 202)
                self.assertTrue(sleep_started.wait(timeout=2))

                progress = client.get(
                    f"/api/simulation/{simulation_response.json['run_id']}"
                )
                self.assertEqual(progress.status_code, 200)
                self.assertEqual(progress.json["processes"][0]["status"], "Processing")
                self.assertEqual(progress.json["processes"][1]["status"], "Queued")
                self.assertIsNone(progress.json["processes"][0]["matches"])
                self.assertIsNone(progress.json["processes"][1]["matches"])
                release_sleep.set()

                for _ in range(100):
                    progress = client.get(
                        f"/api/simulation/{simulation_response.json['run_id']}"
                    )
                    if progress.json["status"] == "completed":
                        break
                    Event().wait(0.01)

            self.assertEqual(progress.json["status"], "completed")
            completed_process = progress.json["result"]["processes"][0]
            completed_second_process = progress.json["result"]["processes"][1]
            self.assertEqual(completed_process["matches"], 3)
            self.assertEqual(
                completed_process["match_positions"],
                [0, 1, 2],
            )
            self.assertEqual(completed_second_process["matches"], 3)
            self.assertEqual(sleep.call_count, 4)
            self.assertEqual(
                completed_process["estimated_time"],
                2,
            )
        finally:
            live_machines[:] = previous_machines
            live_processes[:] = previous_processes
            app_module.next_process_id = previous_next_process_id

    def test_api_requires_login(self):
        response = flask_app.test_client().get("/api/state")
        self.assertEqual(response.status_code, 401)

    def test_job_priority_includes_signed_in_role_priority(self):
        for role, expected_priority in (
            ("professor", 1.0),
            ("management", 1.5),
            ("student", 2.0),
        ):
            client = flask_app.test_client()
            client.post(
                "/api/auth/login",
                json={
                    "username": role,
                    "password": f"{role}-pass",
                },
            )
            response = client.post(
                "/api/processes",
                json={
                    "name": f"{role.title()} job",
                    "sequence": "ATGC",
                    "pattern": "AT",
                    "priority": 1,
                    "work_units": 2,
                },
            )
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json["priority"], expected_priority)

    def test_text_upload_returns_file_contents_as_sequence(self):
        response = self.client.post(
            "/api/processes/upload",
            data={"file": (BytesIO(b"atgc\nAT"), "sequence.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["sequence"], "atgc\nAT")

    def test_binary_upload_preserves_bytes_for_ascii_signature_matching(self):
        response = self.client.post(
            "/api/processes/upload",
            data={
                "target": "sequence",
                "file": (BytesIO(b"\x00[SIMULATED_FAMILY: DIRMAKER-LAB]"), "sample.bin"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["binary"])
        self.assertEqual(
            response.json["sequence"].encode("latin-1"),
            b"\x00[SIMULATED_FAMILY: DIRMAKER-LAB]",
        )

    def test_json_pattern_upload_extracts_signature_array(self):
        response = self.client.post(
            "/api/processes/upload",
            data={
                "target": "pattern",
                "file": (
                    BytesIO(
                        b'{"signatures":[{"name":"family","pattern_ascii":"[SIMULATED_FAMILY: DIRMAKER-LAB]"}]}'
                    ),
                    "signatures.json",
                ),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json["patterns"],
            [
                {
                    "name": "family",
                    "pattern": "[SIMULATED_FAMILY: DIRMAKER-LAB]",
                }
            ],
        )

    def test_sample_json_file_upload_extracts_all_signatures(self):
        signature_file = (
            Path(__file__).resolve().parents[1]
            / "TestSamples"
            / "signatures.json"
        )
        with signature_file.open("rb") as file:
            response = self.client.post(
                "/api/processes/upload",
                data={
                    "target": "pattern",
                    "file": (file, signature_file.name),
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["patterns"]), 4)
        self.assertEqual(
            response.json["patterns"][0]["pattern"],
            "[SIMULATED_FAMILY: DIRMAKER-LAB]",
        )

    def test_sequence_upload_accepts_multiple_files_with_file_metadata(self):
        response = self.client.post(
            "/api/processes/upload",
            data={
                "files": [
                    (BytesIO(b"atgc"), "first.txt"),
                    (BytesIO(b"\x00\xff"), "second.bin"),
                ],
                "target": "sequence",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["sequences"]), 2)
        self.assertEqual(response.json["sequences"][0]["file"]["filename"], "first.txt")
        self.assertEqual(response.json["sequences"][1]["sequence"].encode("latin-1"), b"\x00\xff")
        self.assertTrue(response.json["sequences"][1]["binary"])

    def test_batch_process_submission_creates_one_process_per_sequence(self):
        previous_processes = live_processes[:]
        previous_next_process_id = app_module.next_process_id
        live_processes.clear()
        app_module.next_process_id = 20
        processes_patch = patch("app.storage.save_processes")
        save_processes = processes_patch.start()
        self.addCleanup(processes_patch.stop)

        try:
            response = self.client.post(
                "/api/processes/batch",
                json={
                    "name": "Scan",
                    "pattern": "AA",
                    "priority": 1,
                    "work_units": 4,
                    "pattern_file": {"filename": "signatures.txt", "size": 2},
                    "sequences": [
                        {
                            "sequence": "aatt",
                            "sequence_binary": False,
                            "sequence_file": {"filename": "one.txt", "size": 4},
                        },
                        {
                            "sequence": "\u0000\u00ff",
                            "sequence_binary": True,
                            "sequence_file": {"filename": "two.bin", "size": 2},
                        },
                    ],
                },
            )

            self.assertEqual(response.status_code, 201)
            self.assertEqual([item["id"] for item in response.json["processes"]], [20, 21])
            self.assertEqual(response.json["processes"][0]["name"], "Scan - one.txt")
            self.assertEqual(response.json["processes"][1]["sequence"], "\u0000\u00ff")
            self.assertEqual(response.json["processes"][1]["pattern_filename"], "signatures.txt")
            self.assertEqual(len(live_processes), 2)
            save_processes.assert_called_once()
        finally:
            live_processes[:] = previous_processes
            app_module.next_process_id = previous_next_process_id

    def test_machine_can_be_updated_and_deleted(self):
        previous_machines = live_machines[:]
        previous_next_machine_id = app_module.next_machine_id
        live_machines[:] = [Machine(7, "Old VM", 4)]
        app_module.next_machine_id = 8
        delete_patch = patch("app.storage.delete_machine")
        delete_machine = delete_patch.start()
        self.addCleanup(delete_patch.stop)

        try:
            update = self.client.put(
                "/api/machines/7",
                json={"name": "Fast VM", "capacity": 12},
            )
            self.assertEqual(update.status_code, 200)
            self.assertEqual(update.json["name"], "Fast VM")
            self.assertEqual(live_machines[0].capacity, 12)

            deleted = self.client.delete("/api/machines/7")
            self.assertEqual(deleted.status_code, 200)
            self.assertEqual(live_machines, [])
            delete_machine.assert_called_once_with(7)
        finally:
            live_machines[:] = previous_machines
            app_module.next_machine_id = previous_next_machine_id

    def test_completed_process_can_be_reset_for_another_run(self):
        previous_processes = live_processes[:]
        completed = make_process(5, 4)
        completed.status = "Completed"
        completed.matches = [0, 1]
        completed.signature_matches = [[0, 1]]
        live_processes[:] = [completed]

        try:
            response = self.client.post("/api/processes/5/reset")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["status"], "Queued")
            self.assertIsNone(response.json["matches"])
            self.assertEqual(response.json["allocated_vm"], None)
            app_module.storage.save_process.assert_called()
        finally:
            live_processes[:] = previous_processes

    def test_dataset_returns_persisted_file_and_signature_statistics(self):
        with patch(
            "app.storage.load_dataset",
            return_value=[
                {
                    "id": 6,
                    "name": "Archived scan",
                    "matches": 2,
                    "status": "Completed",
                    "sequence_filename": "archive.bin",
                    "sequence_size": 20,
                    "pattern_filename": "signatures.json",
                    "pattern_size": 12,
                    "signature_results": [
                        {"name": "family", "match_count": 2}
                    ],
                    "content_available": False,
                }
            ],
        ):
            response = self.client.get("/api/dataset")

        self.assertEqual(response.status_code, 200)
        record = response.json["processes"][0]
        self.assertEqual(record["sequence_filename"], "archive.bin")
        self.assertEqual(record["signature_results"][0]["match_count"], 2)
        self.assertFalse(record["content_available"])
        self.assertTrue(response.json["chart"].startswith("data:image/png;base64,"))

    def test_simulation_matches_each_uploaded_signature(self):
        previous_machines = live_machines[:]
        previous_processes = live_processes[:]
        previous_simulation_state = app_module.simulation_state.copy()
        machine = Machine(1, "VM", 100)
        process = Process(
            id=1,
            name="Signature scan",
            sequence="xx[SIMULATED_FAMILY: DIRMAKER-LAB]yyLAB_MARKER",
            pattern="[SIMULATED_FAMILY: DIRMAKER-LAB]",
            priority=1,
            work_units=1,
            patterns=[
                {
                    "name": "family",
                    "pattern": "[SIMULATED_FAMILY: DIRMAKER-LAB]",
                },
                {"name": "marker", "pattern": "LAB_MARKER"},
            ],
        )
        live_machines[:] = [machine]
        live_processes[:] = [process]
        result = app_module.run_simulation(
            "FCFS",
            2,
            [Machine(1, "VM", 100)],
            [Process(
                id=1,
                name="Signature scan",
                sequence=process.sequence,
                pattern=process.pattern,
                priority=1,
                work_units=1,
                patterns=process.patterns,
            )],
        )
        app_module.simulation_state.update(id="signature-test", status="running")

        try:
            with patch("kmp.time.sleep"):
                app_module.execute_processes("signature-test", result, {1: 100})

            self.assertEqual(process.signature_matches, [[2], [36]])
            self.assertEqual(process.allocated_vm, "VM")
            response = app_module.process_dict(process)
            self.assertEqual(response["matches"], 2)
            self.assertEqual(response["allocated_vm"], "VM")
            self.assertNotIn("signature_matches", response)
        finally:
            live_machines[:] = previous_machines
            live_processes[:] = previous_processes
            app_module.simulation_state.update(previous_simulation_state)

    def test_simulation_does_not_reschedule_completed_processes(self):
        previous_machines = live_machines[:]
        previous_processes = live_processes[:]
        previous_next_process_id = app_module.next_process_id
        previous_simulation_state = app_module.simulation_state.copy()
        live_machines[:] = [Machine(1, "VM", 10)]
        completed = make_process(1, 5)
        completed.status = "Completed"
        completed.matches = [0]
        queued = make_process(2, 5)
        live_processes[:] = [completed, queued]
        app_module.next_process_id = 3

        try:
            with patch(
                "app.run_simulation",
                return_value={
                    "allocations": [],
                    "metrics": {},
                    "machines": [],
                    "processes": [],
                },
            ) as run_simulation, patch("app.Thread") as thread:
                response = self.client.post(
                    "/api/simulate",
                    json={"algorithm": "FCFS"},
                )

            self.assertEqual(response.status_code, 202)
            scheduled_processes = run_simulation.call_args.args[3]
            self.assertEqual([process.id for process in scheduled_processes], [2])
            self.assertEqual(completed.status, "Completed")
            self.assertEqual(completed.matches, [0])
            thread.return_value.start.assert_called_once_with()
        finally:
            live_machines[:] = previous_machines
            live_processes[:] = previous_processes
            app_module.next_process_id = previous_next_process_id
            app_module.simulation_state.update(previous_simulation_state)

    def test_simulation_rejects_when_all_processes_are_completed(self):
        previous_machines = live_machines[:]
        previous_processes = live_processes[:]
        live_machines[:] = [Machine(1, "VM", 10)]
        completed = make_process(1, 5)
        completed.status = "Completed"
        live_processes[:] = [completed]

        try:
            with patch("app.run_simulation") as run_simulation:
                response = self.client.post(
                    "/api/simulate",
                    json={"algorithm": "FCFS"},
                )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(completed.status, "Completed")
            run_simulation.assert_not_called()
        finally:
            live_machines[:] = previous_machines
            live_processes[:] = previous_processes

    def test_state_refresh_reloads_machines_and_processes(self):
        with patch(
            "app.storage.load_state",
            return_value=([Machine(7, "Shared VM", 12)], []),
        ) as load_state, patch(
            "app.storage.next_process_id", return_value=8
        ), patch("app.storage.next_machine_id", return_value=8):
            response = self.client.get("/api/state")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["machines"][0]["id"], 7)
        load_state.assert_called_once_with()

    def test_process_storage_leaves_sequence_and_pattern_empty(self):
        class Cursor:
            values = None

            def execute(self, _query, values):
                self.values = values

        cursor = Cursor()
        storage._save_process(cursor, make_process(1, 4))

        self.assertIsNone(cursor.values[2])
        self.assertIsNone(cursor.values[3])

    def test_process_storage_saves_per_signature_counts_and_positions(self):
        process = make_process(2, 4)
        process.status = "Completed"
        process.patterns = [
            {"name": "first", "pattern": "AA"},
            {"name": "second", "pattern": "AT"},
        ]
        process.signature_matches = [[0, 1], [3]]

        class Cursor:
            values = None

            def execute(self, _query, values):
                self.values = values

        cursor = Cursor()
        storage._save_process(cursor, process)
        saved = json.loads(cursor.values[9])

        self.assertEqual(
            saved,
            [
                {
                    "name": "first",
                    "match_count": 2,
                    "match_positions": [0, 1],
                },
                {
                    "name": "second",
                    "match_count": 1,
                    "match_positions": [3],
                },
            ],
        )

    def test_file_record_storage_saves_metadata_only(self):
        process = make_process(3, 5)
        process.sequence_filename = "sequence.bin"
        process.sequence_size = 12
        process.pattern_filename = "signatures.json"
        process.pattern_size = 34

        class Cursor:
            def __init__(self):
                self.calls = []

            def execute(self, query, values):
                self.calls.append((query, values))

        cursor = Cursor()
        storage._save_file_records(cursor, process)

        self.assertEqual(len(cursor.calls), 2)
        self.assertEqual(cursor.calls[0][1], (3, "sequence", "sequence.bin", 12))
        self.assertEqual(cursor.calls[1][1], (3, "pattern", "signatures.json", 34))
        self.assertNotIn(process.sequence, repr(cursor.calls))

    def test_process_content_migration_makes_columns_nullable_and_clears_rows(self):
        class Cursor:
            queries = []

            def execute(self, query):
                self.queries.append(query)

            def fetchall(self):
                return [("sequence_data", "NO"), ("pattern_text", "NO")]

        cursor = Cursor()
        storage._clear_process_content(cursor)

        self.assertTrue(
            any("MODIFY sequence_data MEDIUMTEXT NULL" in query for query in cursor.queries)
        )
        self.assertTrue(
            any("MODIFY pattern_text VARCHAR(255) NULL" in query for query in cursor.queries)
        )
        self.assertTrue(
            any(
                "UPDATE processes SET sequence_data = NULL, pattern_text = NULL" in query
                for query in cursor.queries
            )
        )


if __name__ == "__main__":
    unittest.main()
