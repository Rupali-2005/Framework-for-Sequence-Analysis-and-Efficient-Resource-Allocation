// Local mirror of what the server knows, so we can redraw the page
// without re-fetching everything on every small change.
const state = {
  machines: [],
  processes: [],
};

const $ = (id) => document.getElementById(id);

// Escapes text before it goes into innerHTML, so a process name like
// "<script>" can't break the page or run as code.
function esc(value) {
  return String(value).replace(/[&<>]/g, (c) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
  }[c]));
}

// Small wrapper around fetch: sends JSON, reads JSON back, and turns
// a non-2xx response into a thrown error with the server's message.
async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || 'Something went wrong.');
  }
  return data;
}

// Redraws the machine list and the process table from `state`.
// Doesn't talk to the server — just renders whatever state already has.
function render() {
  $('machines').innerHTML = state.machines.length
    ? state.machines.map((m) => `
        <article class="machine">
          <strong>${esc(m.name)}</strong>
          <span>${m.capacity} units/s</span>
          <small>Ready queue: ${m.queue?.length || 0}</small>
        </article>
      `).join('')
    : '<p class="muted">No virtual machines added.</p>';

  $('processes').innerHTML = state.processes.length
    ? state.processes.map((p) => `
        <tr>
          <td>${p.id}</td>
          <td>${esc(p.name)}</td>
          <td>${p.matches ?? '—'}</td>
          <td>${p.priority}</td>
          <td>${p.estimated_time ?? '—'}</td>
          <td>${p.status || 'Queued'}</td>
        </tr>
      `).join('')
    : '<tr><td colspan="6" class="muted">No submitted processes.</td></tr>';
}

// One metrics object -> the little card grid used for a single run.
function metricsCards(metrics) {
  const utilization = Object.entries(metrics.machine_utilization || {})
    .map(([name, pct]) => `<div class="metric"><strong>${esc(name)}</strong><span>${pct}% busy</span></div>`)
    .join('');

  return `
    <div class="metric"><strong>Avg waiting time</strong><span>${metrics.average_waiting_time}</span></div>
    <div class="metric"><strong>Avg turnaround time</strong><span>${metrics.average_turnaround_time}</span></div>
    <div class="metric"><strong>Makespan</strong><span>${metrics.makespan}</span></div>
    ${utilization}
  `;
}

// Renders the result of a single simulation run.
function renderSimulationResult(result) {
  $('metrics').innerHTML = `<p class="muted">Algorithm: ${esc(result.algorithm)}</p>${metricsCards(result.metrics)}`;
}

// Renders the result of "Compare all" — one labelled group per algorithm.
function renderComparison(results) {
  $('metrics').innerHTML = Object.entries(results)
    .map(([algorithm, metrics]) => `
      <p class="muted" style="width:100%">${esc(algorithm)}</p>
      ${metricsCards(metrics)}
    `).join('');
}

// Pulls the current machines/processes from the server. Used on page
// load so a refresh doesn't lose what's already been submitted.
async function loadState() {
  const data = await api('/api/state');
  state.machines = data.machines;
  state.processes = data.processes;
  render();
}

// "Add virtual machine" — sends the form fields to the backend and
// adds whatever machine object it hands back.
$('machine-form').onsubmit = async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);

  try {
    const machine = await api('/api/machines', {
      method: 'POST',
      body: JSON.stringify({
        name: f.get('name'),
        capacity: f.get('capacity'),
      }),
    });
    state.machines.push(machine);
    e.target.reset();
    $('message').textContent = 'Virtual machine added.';
    render();
  } catch (err) {
    $('message').textContent = err.message;
  }
};

// "Submit process" — sends the form fields to the backend, which runs
// the KMP pattern match immediately and hands back the full process.
$('process-form').onsubmit = async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);

  try {
    const process = await api('/api/processes', {
      method: 'POST',
      body: JSON.stringify({
        name: f.get('name'),
        sequence: f.get('sequence'),
        pattern: f.get('pattern'),
        priority: f.get('priority'),
        work_units: f.get('work_units'),
      }),
    });
    state.processes.push(process);
    e.target.reset();
    $('message').textContent = 'Process added.';
    render();
  } catch (err) {
    $('message').textContent = err.message;
  }
};

// "Start simulation" — runs the selected algorithm on the server and
// refreshes machines/processes/metrics with the result.
$('run').addEventListener('click', async () => {
  try {
    const result = await api('/api/simulate', {
      method: 'POST',
      body: JSON.stringify({ algorithm: $('algorithm').value }),
    });
    state.machines = result.machines;
    state.processes = result.processes;
    render();
    renderSimulationResult(result);
    $('message').textContent = `Simulation run with ${result.algorithm}.`;
  } catch (err) {
    $('message').textContent = err.message;
  }
});

// "Compare all" — runs FCFS, SJF, and Priority on the server and
// shows all three sets of metrics side by side.
$('compare').addEventListener('click', async () => {
  try {
    const results = await api('/api/compare', { method: 'POST' });
    renderComparison(results);
    $('message').textContent = 'Compared all algorithms.';
  } catch (err) {
    $('message').textContent = err.message;
  }
});

// On page load: pull whatever the server already has (handles refresh)
// and draw the initial empty-state placeholders if there's nothing yet.
loadState().catch((err) => {
  $('message').textContent = err.message;
});