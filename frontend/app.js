const state={machines:[],processes:[],machineId:1,processId:1};
const $=id=>document.getElementById(id); const esc=value=>String(value).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function render(){
 $('machines').innerHTML=state.machines.length?state.machines.map(m=>`<article class="machine"><strong>${esc(m.name)}</strong><span>${m.capacity} units/s</span><small>Ready queue: ${m.queue?.length||0}</small></article>`).join(''):'<p class="muted">No virtual machines added.</p>';
 $('processes').innerHTML=state.processes.length?state.processes.map(p=>`<tr><td>${p.id}</td><td>${esc(p.name)}</td><td>${p.matches??'—'}</td><td>${p.priority}</td><td>${p.estimated_time??'—'}</td><td>${p.status||'Queued'}</td></tr>`).join(''):'<tr><td colspan="6" class="muted">No submitted processes.</td></tr>';
}
$('machine-form').onsubmit=e=>{e.preventDefault();let f=new FormData(e.target);state.machines.push({id:state.machineId++,name:f.get('name'),capacity:+f.get('capacity'),queue:[]});e.target.reset();$('message').textContent='Virtual machine added.';render()};
$('process-form').onsubmit=e=>{e.preventDefault();let f=new FormData(e.target), seq=f.get('sequence').replace(/\s/g,'');state.processes.push({id:state.processId++,name:f.get('name'),sequence:seq,pattern:f.get('pattern'),priority:+f.get('priority'),work_units:+f.get('work_units'),status:'Queued'});e.target.reset();$('message').textContent='Process added locally. Start the Python backend for simulation.';render()};
render();
