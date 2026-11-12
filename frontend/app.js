const state = {
  machines: [],
  processes: [],
  uploadedSequences: [],
  uploadedPatterns: [],
  patternFile: null,
};

const element = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;",
  })[character]);
}

async function api(path, options = {}) {
  const headers = options.body instanceof FormData
    ? {}
    : { "Content-Type": "application/json" };
  const response = await fetch(path, {
    ...options,
    headers: { ...headers, ...options.headers },
  });
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || "Something went wrong.");
  }

  return data;
}

function render() {
  element("machines").innerHTML = state.machines.length
    ? state.machines.map((machine) => `
        <article class="machine">
          <form class="machine-edit" data-machine-id="${machine.id}">
            <label>
              Name
              <input name="name" value="${escapeHtml(machine.name)}" required maxlength="100">
            </label>
            <label>
              Capacity (units/s)
              <input name="capacity" type="number" min="1" value="${machine.capacity}" required>
            </label>
            <button type="submit">Save</button>
            <button class="secondary delete-machine" type="button" data-machine-id="${machine.id}">Delete</button>
          </form>
          <small>Ready queue: ${machine.queue?.length || 0}</small>
        </article>
      `).join("")
    : '<p class="muted">No virtual machines added.</p>';

  element("processes").innerHTML = state.processes.length
    ? state.processes.map((process) => `
        <tr>
          <td>${process.id}</td>
          <td>
            ${escapeHtml(process.name)}
            ${process.sequence_filename
              ? `<small class="muted file-name">${escapeHtml(process.sequence_filename)}</small>`
              : ""}
          </td>
          <td>${process.work_units}</td>
          <td>${process.matches ?? "—"}</td>
          <td>${escapeHtml(process.allocated_vm || "—")}</td>
          <td>${Number(process.priority).toFixed(2)}</td>
          <td>${process.estimated_time ?? "—"}</td>
          <td>${escapeHtml(process.status || "Queued")}</td>
          <td>
            ${["Completed", "Failed"].includes(process.status)
              ? `<button class="secondary reset-process" type="button" data-process-id="${process.id}">Requeue</button>`
              : "—"}
          </td>
        </tr>
        ${process.signature_results?.length
          ? `<tr class="signature-row"><td colspan="9"><details>
              <summary>Signature details (${process.signature_results.length})</summary>
              <ul>${process.signature_results.map((result) => `
                <li>${escapeHtml(result.name)}: ${result.matches} match(es)
                  ${result.match_positions?.length
                    ? `at ${result.match_positions.join(", ")}`
                    : ""}
                </li>
              `).join("")}</ul>
            </details></td></tr>`
          : ""}
      `).join("")
    : '<tr><td colspan="9" class="muted">No submitted processes.</td></tr>';
}

function renderDataset(records) {
  element("dataset").innerHTML = records.length
    ? records.map((record) => {
      const signatureSummary = record.signature_results?.length
        ? record.signature_results.map((result) =>
          `${escapeHtml(result.name)}: ${result.matches ?? result.match_count ?? 0}`,
        ).join("<br>")
        : "—";
      const sequenceFile = record.sequence_filename
        ? `${escapeHtml(record.sequence_filename)} (${record.sequence_size ?? 0} bytes)`
        : "—";
      const patternFile = record.pattern_filename
        ? `${escapeHtml(record.pattern_filename)} (${record.pattern_size ?? 0} bytes)`
        : "—";
      return `
        <tr>
          <td>${escapeHtml(record.name)}</td>
          <td>${sequenceFile}</td>
          <td>${patternFile}</td>
          <td>${signatureSummary}</td>
          <td>${escapeHtml(record.status)}</td>
          <td>${record.content_available ? "Available for requeue" : "Metadata only"}</td>
        </tr>
      `;
    }).join("")
    : '<tr><td colspan="6" class="muted">No file records found.</td></tr>';
}

function metricCards(metrics) {
  const summaryMetrics = [
    ["Average waiting time", metrics.average_waiting_time],
    ["Average turnaround time", metrics.average_turnaround_time],
    ["Makespan", metrics.makespan],
    ["Throughput", metrics.throughput],
  ];
  const summary = summaryMetrics.map(([label, value]) => `
    <div class="metric">
      <strong>${label}</strong>
      <span>${value}</span>
    </div>
  `).join("");
  const utilization = Object.entries(metrics.machine_utilization || {})
    .map(([name, percentage]) => `
      <div class="metric">
        <strong>${escapeHtml(name)}</strong>
        <span>${percentage}% busy</span>
      </div>
    `).join("");

  return `${summary}${utilization}`;
}

function renderSimulationResult(result) {
  element("metrics").innerHTML = `
    <p class="dashboard-caption">Algorithm: ${escapeHtml(result.algorithm)}</p>
    <div class="metrics">${metricCards(result.metrics)}</div>
  `;
}

function renderComparison({ results, chart }) {
  const utilizationCards = Object.entries(results).map(
    ([algorithm, metrics]) => {
      const machineMetrics = Object.entries(metrics.machine_utilization || {})
        .map(([machine, percentage]) => `
          <span class="utilization-chip">
            ${escapeHtml(machine)} <strong>${percentage}%</strong>
          </span>
        `).join("");

      return `
        <article class="utilization-card">
          <h3>${escapeHtml(algorithm)}</h3>
          <div class="utilization-list">
            ${machineMetrics || '<span class="muted">No machine data.</span>'}
          </div>
        </article>
      `;
    },
  ).join("");

  element("metrics").innerHTML = `
    <p class="dashboard-caption">
      Compared with Round Robin quantum ${escapeHtml(element("time-quantum").value)}.
      Lower waiting time, turnaround time, and makespan are better.
    </p>
    <img class="metrics-chart" src="${chart}"
         alt="Bar chart comparing waiting time, turnaround time, and makespan across scheduling algorithms">
    <h3 class="section-heading">Machine utilization</h3>
    <div class="utilization-grid">${utilizationCards}</div>
  `;
}

function currentTimeQuantum() {
  const timeQuantum = Number(element("time-quantum").value);
  if (!Number.isFinite(timeQuantum) || timeQuantum <= 0) {
    throw new Error("Round Robin quantum must be greater than zero.");
  }
  return timeQuantum;
}

async function loadState() {
  const data = await api("/api/state");
  state.machines = data.machines;
  state.processes = data.processes;
  render();
}

async function loadDataset() {
  const data = await api("/api/dataset");
  renderDataset(data.processes);
  const chart = element("dataset-chart");
  chart.src = data.chart;
  chart.hidden = false;
}

function showApplication(auth) {
  element("login-panel").hidden = auth.authenticated;
  element("application").hidden = !auth.authenticated;
  if (auth.authenticated) {
    element("current-role").textContent =
      `${auth.role} (role priority ${auth.role_priority})`;
  }
}

function pause(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitForSimulation(runId) {
  while (true) {
    const progress = await api(`/api/simulation/${encodeURIComponent(runId)}`);
    state.processes = progress.processes;
    state.machines = progress.machines;
    render();

    if (progress.status === "completed") {
      return progress.result;
    }
    if (progress.status === "failed") {
      throw new Error(progress.error || "Simulation failed.");
    }

    await pause(250);
  }
}

element("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);

  try {
    const auth = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: form.get("username"),
        password: form.get("password"),
      }),
    });
    showApplication(auth);
    event.target.reset();
    element("login-message").textContent = "";
    try {
      await Promise.all([loadState(), loadDataset()]);
      element("message").textContent =
        "Signed in. Shared virtual machines are available to every role.";
    } catch (error) {
      element("message").textContent = error.message;
    }
  } catch (error) {
    element("login-message").textContent = error.message;
  }
});

element("logout").addEventListener("click", async () => {
  try {
    await api("/api/auth/logout", { method: "POST" });
    showApplication({ authenticated: false });
    element("login-message").textContent = "You have signed out.";
  } catch (error) {
    element("message").textContent = error.message;
  }
});

async function loadFilesIntoForm(input, fieldName) {
  const files = Array.from(input.files);
  if (!files.length) return;
  try {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    form.append("target", fieldName);
    const data = await api("/api/processes/upload", {
      method: "POST",
      body: form,
    });
    if (fieldName === "pattern") {
      state.patternFile = data.file;
      state.uploadedPatterns = data.patterns || [];
      element("pattern").value = state.uploadedPatterns.length
        ? state.uploadedPatterns[0].pattern
        : data.sequence;
      element("pattern-file-info").textContent = state.uploadedPatterns.length
        ? `${files[0].name}: ${state.uploadedPatterns.length} signatures loaded.`
        : files[0].name;
      element("message").textContent = state.uploadedPatterns.length
        ? `Loaded ${state.uploadedPatterns.length} signatures from ${files[0].name}.`
        : `Loaded ${files[0].name} as a single pattern.`;
    } else {
      const sequences = data.sequences || [{
        sequence: data.sequence,
        binary: data.binary === true,
        file: data.file,
      }];
      state.uploadedSequences = sequences.map((item) => ({
        sequence: item.sequence,
        sequence_binary: item.binary,
        sequence_file: item.file,
      }));
      element("sequence-file-info").textContent =
        state.uploadedSequences.map((item) => item.sequence_file.filename).join(", ");
      element("message").textContent =
        `Loaded ${state.uploadedSequences.length} sequence file(s).`;
    }
  } catch (error) {
    element("message").textContent = error.message;
  } finally {
    input.value = "";
  }
}

element("sequence-file").addEventListener("change", (event) => {
  loadFilesIntoForm(event.target, "sequence");
});

element("pattern-file").addEventListener("change", (event) => {
  loadFilesIntoForm(event.target, "pattern");
});

element("machine-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);

  try {
    const machine = await api("/api/machines", {
      method: "POST",
      body: JSON.stringify({
        name: form.get("name"),
        capacity: form.get("capacity"),
      }),
    });
    state.machines.push(machine);
    event.target.reset();
    element("message").textContent = "Virtual machine added.";
    render();
  } catch (error) {
    element("message").textContent = error.message;
  }
});

element("machines").addEventListener("submit", async (event) => {
  if (!event.target.matches(".machine-edit")) return;
  event.preventDefault();
  const form = new FormData(event.target);
  const machineId = event.target.dataset.machineId;
  try {
    const updated = await api(`/api/machines/${encodeURIComponent(machineId)}`, {
      method: "PUT",
      body: JSON.stringify({
        name: form.get("name"),
        capacity: form.get("capacity"),
      }),
    });
    state.machines = state.machines.map((machine) =>
      machine.id === updated.id ? { ...machine, ...updated } : machine,
    );
    await loadState();
    element("message").textContent = "Virtual machine updated.";
  } catch (error) {
    element("message").textContent = error.message;
  }
});

element("machines").addEventListener("click", async (event) => {
  const button = event.target.closest(".delete-machine");
  if (!button) return;
  try {
    await api(`/api/machines/${encodeURIComponent(button.dataset.machineId)}`, {
      method: "DELETE",
    });
    state.machines = state.machines.filter(
      (machine) => machine.id !== Number(button.dataset.machineId),
    );
    await loadState();
    element("message").textContent = "Virtual machine removed.";
  } catch (error) {
    element("message").textContent = error.message;
  }
});

element("process-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);

  try {
    if (!state.uploadedSequences.length) {
      throw new Error("Upload at least one sequence file.");
    }
    const result = await api("/api/processes/batch", {
      method: "POST",
      body: JSON.stringify({
        name: form.get("name"),
        pattern: form.get("pattern"),
        patterns: state.uploadedPatterns.length ? state.uploadedPatterns : undefined,
        pattern_file: state.patternFile,
        priority: form.get("priority"),
        sequences: state.uploadedSequences,
      }),
    });
    state.processes.push(...result.processes);
    state.uploadedSequences = [];
    state.uploadedPatterns = [];
    state.patternFile = null;
    element("sequence-file-info").textContent = "";
    element("pattern-file-info").textContent = "";
    event.target.reset();
    element("message").textContent =
      `Added ${result.processes.length} process(es) from uploaded files.`;
    render();
    try {
      await loadDataset();
    } catch (error) {
      element("message").textContent +=
        ` Dataset refresh failed: ${error.message}`;
    }
  } catch (error) {
    element("message").textContent = error.message;
  }
});

element("processes").addEventListener("click", async (event) => {
  const button = event.target.closest(".reset-process");
  if (!button) return;
  try {
    const process = await api(
      `/api/processes/${encodeURIComponent(button.dataset.processId)}/reset`,
      { method: "POST" },
    );
    state.processes = state.processes.map((item) =>
      item.id === process.id ? process : item,
    );
    render();
    element("message").textContent = `${process.name} queued again.`;
    try {
      await loadDataset();
    } catch (error) {
      element("message").textContent +=
        ` Dataset refresh failed: ${error.message}`;
    }
  } catch (error) {
    element("message").textContent = error.message;
  }
});

element("refresh-dataset").addEventListener("click", async () => {
  try {
    await loadDataset();
    element("message").textContent = "Dataset refreshed.";
  } catch (error) {
    element("message").textContent = error.message;
  }
});

element("run").addEventListener("click", async () => {
  const runButton = element("run");
  runButton.disabled = true;
  element("message").textContent =
    "Processing jobs. Matching pauses for one second after each VM-capacity batch of sequence characters.";

  try {
    const started = await api("/api/simulate", {
      method: "POST",
      body: JSON.stringify({
        algorithm: element("algorithm").value,
        time_quantum: currentTimeQuantum(),
      }),
    });
    const result = await waitForSimulation(started.run_id);
    state.machines = result.machines.map((machine) => ({
      ...machine,
      queue: machine.ready_queue,
    }));
    state.processes = result.processes;
    render();
    renderSimulationResult(result);
    element("message").textContent = `Simulation run with ${result.algorithm}.`;
    try {
      await loadDataset();
    } catch (error) {
      element("message").textContent +=
        ` Dataset refresh failed: ${error.message}`;
    }
  } catch (error) {
    element("message").textContent = error.message;
    try {
      await Promise.all([loadState(), loadDataset()]);
    } catch (stateError) {
      element("message").textContent =
        `${error.message} Could not refresh process status: ${stateError.message}`;
    }
  } finally {
    runButton.disabled = false;
  }
});

element("compare").addEventListener("click", async () => {
  try {
    const comparison = await api("/api/compare", {
      method: "POST",
      body: JSON.stringify({ time_quantum: currentTimeQuantum() }),
    });
    renderComparison(comparison);
    element("message").textContent = "Compared all algorithms.";
  } catch (error) {
    element("message").textContent = error.message;
  }
});

api("/api/auth/status").then(async (auth) => {
  showApplication(auth);
  if (auth.authenticated) {
    await Promise.all([loadState(), loadDataset()]);
  }
}).catch((error) => {
  element("login-message").textContent = error.message;
});
