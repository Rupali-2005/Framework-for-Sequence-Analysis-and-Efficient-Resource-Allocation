# FESARA-Framework for Efficient Sequential Analysis and Resource Allocation

## Description

FESARA is a systems level framework that processes long,sequential data (DNA-style,protein-style,byte streamsor any other sequential input) in scheduled batches.It simulates a configurable multi-processor environment where jobs are queued,scheduled by priority and analyzed for patterns while all jobs,resources and result data is persisted and managed through a relational database.

This project combines the concepts of Operating System and Database Management System. It needs a scheduler that shares limited processor and memory resources among competing jobs and correctly handles resource contention and deadlock,along with a database layer that avoids duplicate storage of input data,handles concurrent updates safely and can fully recover its state after a failure.

## Problem Statement / Objective

Multiple users submit large sequential-data jobs which compete for limited CPU and memory in a resource-constrained environment.Existing tools address only one half of this problem.Priority schedulers handle resource allocation and queuing but ignore data duplication and crash recovery while sequence-analysis pipelines handle the data processing but hand scheduling off to an external system and rarely account for deadlock or optimal resource allocation.

FESARA's objective is to bring both halves together in one system:

- Build a scheduler that assigns limited processor and memory resources to competing jobs based on priority,without exceeding configured limits
- Run multiple jobs concurrently using worker threads with shared resources tracked safely
- Deliberately construct,detect and resolve a deadlock scenario
- Design a relational schema that avoids storing duplicate input data,supports safe concurrent updates to job state and can fully reconstruct system state after a crash

## Team Members  
- *Rupali Rana(Leader)*
- *Parth Batham*
- *Aryan Rawat*

## Technologies / Tools Used

- **Frontend:** HTML,CSS,JavaScript 
- **Backend (planned):** Python,FastAPI
- **Database (planned):** MySQL
- **Version control:** Git/ GitHub
- **IDE:** VS Code

## Project Setup / Installation Instructions


## Major Features / Modules

### Frontend
- **Add Virtual Machine**-form to register a simulated processor with a name and processing capacity (units/s).
- **Submit Process**-form to submit a job: name,sequence data,pattern to search for,priority and work units.
- **Scheduling algorithm selector**-dropdown to choose between FCFS,SJFand Priority scheduling .
- **Machine allocation view**-live display of each registered machine and its current ready-queue length.
- **Process table**-live table of every submitted process,showing pattern matches,priority,estimated timeand status.
- **Metrics dashboard placeholder**-reserved section for simulation results once the backend is connected.

## Current Project Status / Progress

**Phase: Early development-frontend only.**

- Frontend UI built:machine registration,process submission,scheduling algorithm selectorand live (client-side only) rendering of machines and processes.
- No backend or database is connected yet-submitted machines and processes are currently held only in the browser's local state and are not scheduled,analyzedor persisted.
- "Start simulation" and "Compare all" controls exist in the interface but are not yet wired to any logic.
- Backend (FastAPI + scheduling/deadlock logic) and database (MySQL schema,dedup,transactions,recovery) are the next major milestones.

---  
## Initial ER Model
<img width="1275" height="1650" alt="ER_Image" src="https://github.com/user-attachments/assets/3dbc08bf-ddd2-47ee-b170-c50cf4ffd142" />

