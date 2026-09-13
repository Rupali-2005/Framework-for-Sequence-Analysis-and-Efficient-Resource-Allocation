CREATE DATABASE IF NOT EXISTS fesara;
USE fesara;

CREATE TABLE IF NOT EXISTS machines (
  id INT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  capacity INT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS processes (
  id INT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  sequence_data MEDIUMTEXT NOT NULL,
  pattern_text VARCHAR(255) NOT NULL,
  priority INT NOT NULL,
  work_units INT NOT NULL,
  match_count INT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'Queued',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS simulation_runs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  algorithm VARCHAR(20) NOT NULL,
  average_waiting_time DECIMAL(10,2) NOT NULL,
  average_turnaround_time DECIMAL(10,2) NOT NULL,
  makespan DECIMAL(10,2) NOT NULL,
  executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS allocations (
  id INT AUTO_INCREMENT PRIMARY KEY,
  run_id INT NOT NULL,
  process_id INT NOT NULL,
  machine_id INT NOT NULL,
  start_time DECIMAL(10,2) NOT NULL,
  finish_time DECIMAL(10,2) NOT NULL,
  FOREIGN KEY (run_id) REFERENCES simulation_runs(id),
  FOREIGN KEY (process_id) REFERENCES processes(id),
  FOREIGN KEY (machine_id) REFERENCES machines(id)
);
