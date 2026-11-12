# Framework for Efficient Sequential Analysis and Resource Allocation (FESARA)

FESARA is a small Flask application that simulates deterministic allocation of sequence-analysis processes to virtual machines. It uses KMP for sequence pattern matching and provides FCFS, SJF, Priority, Round Robin, and SRTF scheduling.

## Run

```powershell
python -m pip install -r backend\requirements.txt
python backend\app.py
```

Open `http://127.0.0.1:5000` and sign in with one of the three configured accounts. Add, edit, or remove shared machines, then upload up to 10 sequence files (5 MB each) and one pattern file to create a batch of processes. A batch uses the same pattern set and scheduling options for every uploaded sequence. Select an algorithm, then run or compare simulations. Completed processes are not scheduled again automatically; use **Requeue** to run a completed or failed process again while its content is available in memory. Round Robin uses the configurable quantum shown beside the algorithm selector. The metrics dashboard displays Matplotlib-generated graphs for waiting time, turnaround time, makespan, and machine utilization, and reports throughput and per-machine utilization.

Each completed process exposes match counts and positions for every signature. The dataset view lists file metadata, per-signature results, and a graph of total matches per sequence file. It also shows persisted historical process records whose uploaded content is no longer available.

All submitted processes are ready at time zero in the current model. SRTF therefore selects the ready process with the shortest remaining processing time. Work is distributed to the machine with the lowest projected completion time; ties use machine ID, so results are repeatable.

Work units are calculated automatically as the sequence length used for matching multiplied by the number of signatures (one when using a single pattern). This is a scheduling workload estimate, not a measured count of KMP comparisons. Pattern matching is performed when **Start simulation** is pressed, not when a process is submitted or when algorithms are compared. Before a run, estimated time is sequence length multiplied by the number of signatures and divided by the fastest available VM's capacity; when the scheduler assigns a VM, the estimate is updated using that VM's capacity. Each VM processes its assigned jobs in queue order, while jobs on different VMs run concurrently, so up to one job per VM can be `Processing` at a time. During KMP matching, each VM pauses for one second after processing each batch of sequence characters equal to its processing capacity, for each signature; pattern characters do not count toward the batch size. Estimates are approximate and do not include matching overhead.

Run the independent core tests with:

```powershell
python -m unittest discover -s backend
```

## MySQL persistence

The app connects to MySQL on its first request, creates or migrates the configured database tables, and reloads saved machines and processes. Machine configuration, process metadata, uploaded-file names and sizes, per-signature match statistics, individual simulation runs, allocations, and each algorithm in a comparison are saved to MySQL. Removed machines are deactivated so past allocations retain their machine references. If the database cannot be reached, API requests return a database error instead of silently falling back to memory.

The defaults are host `127.0.0.1`, port `3306`, user `root`, an empty password, and database `PBL` (matching `database.sql`). Set `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, and optionally `MYSQL_DATABASE` in `.env` to match your MySQL setup. Ensure that user can create the database and tables on first run, or create the database and grant access beforehand.

Create `backend\.env` and configure `FLASK_SECRET_KEY` plus the three username/password pairs: `PROFESSOR_USERNAME` / `PROFESSOR_PASSWORD`, `MANAGEMENT_USERNAME` / `MANAGEMENT_PASSWORD`, and `STUDENT_USERNAME` / `STUDENT_PASSWORD`. Choose strong, unique passwords and a long random secret key. There is no registration or built-in default password; the app accepts only accounts configured in this file. Role priorities are Professor `1`, Management `2`, and Student `3`. A job's effective priority is the average of its given priority and its submitter's role priority. The virtual machines are shared across all roles.

```powershell
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=your_username
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=PBL
FLASK_SECRET_KEY=your_random_secret
PROFESSOR_USERNAME=professor
PROFESSOR_PASSWORD=choose_a_password
MANAGEMENT_USERNAME=management
MANAGEMENT_PASSWORD=choose_a_password
STUDENT_USERNAME=student
STUDENT_PASSWORD=choose_a_password
```

Machine and process state is refreshed from MySQL whenever the dashboard loads. Sequence and pattern text are entered only by uploading files (up to 5 MB); `.bin` sequence files are matched as raw bytes. A JSON pattern file may provide a `signatures` array; each entry's ASCII `pattern_ascii` is searched separately. The process table shows the total match count and the VM allocated to each completed process.

For privacy, process sequence and pattern content are kept in memory only and are not persisted in MySQL. On startup, the app clears any legacy sequence and pattern values; jobs without that content are omitted from the active process list but remain visible as metadata in the dataset view. A job can be requeued while its content remains in memory; after a server restart, upload it again to run it. File metadata, per-signature match results, and simulation history remain stored.
