# FESARA - Framework for Efficient Sequential Analysis and Resource Allocation

## Description

FESARA is a systems level framework that processes long,sequential data (DNA-style,protein-style,byte streamsor any other sequential input) in scheduled batches.It simulates a configurable multi-processor environment where jobs are queued,scheduled by priority and analyzed for patterns while all jobs,resources and result data is persisted and managed through a relational database.

This project combines the concepts of Operating System and Database Management System. It needs a scheduler that shares limited processor and memory resources among competing jobs and correctly handles resource contention and deadlock,along with a database layer that avoids duplicate storage of input data,handles concurrent updates safely and can fully recover its state after a failure.

## Problem Statement / Objective

Multiple users submit large sequential-data jobs which compete for limited CPU and memory in a resource-constrained environment.Existing tools address only one half of this problem.Priority schedulers handle resource allocation and queuing but ignore data duplication and crash recovery while sequence-analysis pipelines handle the data processing but hand scheduling off to an external system and rarely account for deadlock or optimal resource allocation.

FESARA's objective is to bring both halves together in one system:

- Build a scheduler that assigns limited processor resources to competing jobs in an efficient manner
- Run jobs through a simulated multi-machine environment where processing speed depends on each machine's capacity.
- Comparision and visualization of different scheduling algorithms
- Design a relational schema that avoids storing duplicate input data,supports safe concurrent updates to job state and can fully reconstruct system state after a crash.

## Team Members  
- *Rupali Rana(Leader)*
- *Parth Batham*
- *Aryan Rawat*

## Technologies / Tools Used

- **Frontend:** HTML,CSS,JavaScript (vanilla)
- **Backend:** Python,Flask
- **Database:** MySQL
- **Charts:** matplotlib 
- **Version control:** Git / GitHub
- **IDE:** VS Code

## Project Setup / Installation Instructions

Project structure (frontend and backend sit in sibling folders):

```
PBL/
database.sql
  frontend/
    index.html
    app.js
    style.css
  backend/
    app.py
    charts.py
    kmp.py
    metrics.py
    models.py
    scheduling.py
    storage.py
    requirements.txt
    .env
```

1. **Start your MySQL server.** 
2. **Create a `.env` file inside `backend/`** with your MySQL settings. All of these are optional and fall back to the defaults shown:
   ```
   MYSQL_HOST=127.0.0.1
   MYSQL_PORT=3306
   MYSQL_USER=your_username
   MYSQL_PASSWORD=your_password
   MYSQL_DATABASE=PBL
   ```
3. From inside `backend/`,install dependencies:
   ```
   pip install -r requirements.txt
   ```
   
4. Run the server:
   ```
   python app.py
   ```
5. Open `http://127.0.0.1:5000` in a browser. 


## Major Features / Modules

### Implemented so far
- **Virtual machines** - register a simulated processor with a name and capacity (characters processed per second) 
- **Processes** - submit a job (name,sequence,pattern,priority,work units). Saved to MySQL. 
- **Scheduling algorithms** - `scheduling.py` supports **FCFS,SJF,Priority,Round Robin (RR) and SRTF**
- **Pattern matching (KMP)** - `kmp.py` finds every occurrence (including overlapping ones) of a pattern in linear time using Knuth Morris Pratt Algorithm. 
- **Compare all** - runs all five algorithms on copies of the current machines and processes ,saves each run to MySQL and returns the metrics together with a bar chart comparing different metrics(`charts.py`).
- **Metrics** - `metrics.py` calculates average waiting time,average turnaround time,makespan,throughput and per-machine utilization.
- **MySQL persistence** - `storage.py` creates the schema on first use (`machines`,`processes`,`simulation_runs`,`allocations`),saves every change and reloads machines and processes on server startup. 

### Planned (not yet implemented)
- **Deduplication of input sequences** - identical sequences are still stored separately; no content hashing yet.
- **Append-only event log and crash-recovery replay** - the system reloads its last saved state on startup,but keeps no history of state transitions to replay.
- **Creation and Allocation of Default roles** - to assign default priority on basis of roles

## Current Project Status / Progress

**Phase: Frontend,backend and MySQL persistence working together; five scheduling algorithms with comparison charts in place**

- Machines and processes are created and  reloaded when the server restarts.
- Five scheduling algorithms (FCFS,SJF,Priority,RR,SRTF) are implemented and can be run individually or compared side by side with a generated chart.
- Simulations run in the background with live status polling and each completed run is saved with its metrics and allocations.
- **Not yet started:** optimization of data storage, append only event log and crash recovery, creation of default roles
---
## Initial ER Model  
<img width="1275" height="1650" alt="ER_Image" src="https://github.com/user-attachments/assets/7702d9e6-d3b0-462a-b185-071e55ed4d06" />

