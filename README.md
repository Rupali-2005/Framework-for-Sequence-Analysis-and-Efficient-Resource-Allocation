# Framework for Efficient Sequential Analysis and Resource Allocation (FESARA)

FESARA is a small Flask application that simulates deterministic allocation of sequence-analysis processes to virtual machines. It uses KMP for sequence pattern matching and provides FCFS, SJF, and Priority scheduling.

## Run

```powershell
python -m pip install -r backend\requirements.txt
python backend\app.py
```

Open `http://127.0.0.1:5000`. Add one or more machines and processes, select an algorithm, then run or compare simulations. A process is allocated to the machine with the lowest projected completion time; ties use machine ID, so results are repeatable.

Run the independent core tests with:

```powershell
python -m unittest discover -s backend
```

## MySQL (optional persistence)

The app runs in memory when MySQL is not configured. For local MySQL persistence:

1. Run `mysql -u root -p < database.sql`.
2. Copy `.env.example` to `.env` and fill in the local MySQL password.
3. Restart the Flask app.

Machines, processes, simulation runs, and allocations are then recorded in MySQL.
