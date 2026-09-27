const api = "";

const els = {
  health: document.getElementById("health"),
  title: document.getElementById("title"),
  description: document.getElementById("description"),
  occurred: document.getElementById("occurred"),
  submit: document.getElementById("submit"),
  demo: document.getElementById("demo"),
  status: document.getElementById("status"),
  severity: document.getElementById("severity"),
  confidence: document.getElementById("confidence"),
  malicious: document.getElementById("malicious"),
  node: document.getElementById("node"),
  jevMs: document.getElementById("jevMs"),
  verify: document.getElementById("verify"),
  triage: document.getElementById("triage"),
  hypothesis: document.getElementById("hypothesis"),
  plan: document.getElementById("plan"),
  evidence: document.getElementById("evidence"),
  history: document.getElementById("history"),
  queryA: document.getElementById("queryA"),
  queryB: document.getElementById("queryB"),
  graph: document.getElementById("graph"),
  timeline: document.getElementById("timeline"),
  approve: document.getElementById("approve"),
  reject: document.getElementById("reject"),
  retry: document.getElementById("retry"),
};

let currentId = null;

async function json(path, options) {
  const res = await fetch(api + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || res.statusText);
  return body;
}

async function refreshHealth() {
  try {
    const h = await json("/health");
    els.health.textContent = `stack ${h.status} · neo4j ${h.neo4j} · qdrant ${h.qdrant} · openrouter ${h.openrouter_configured}`;
  } catch (err) {
    els.health.textContent = "API unreachable";
  }
}

function render(incident) {
  currentId = incident.id;
  els.status.textContent = incident.status;
  els.node.textContent = incident.current_node || "—";
  const t = incident.triage;
  els.severity.textContent = t ? t.severity : "—";
  els.confidence.textContent = t ? t.confidence.toFixed(3) : "—";
  els.malicious.textContent = t ? String(t.is_malicious) : "—";
  els.jevMs.textContent = t && t.jev_latency_ms ? `${Math.round(t.jev_latency_ms)} ms` : "—";
  els.verify.textContent = incident.verification_status || "—";
  els.triage.textContent = JSON.stringify(t || incident.error || "no triage", null, 2);
  els.hypothesis.textContent = incident.rca
    ? `${incident.rca.root_cause_hypothesis} (confidence ${incident.rca.confidence})`
    : "—";
  els.plan.innerHTML = (incident.remediation_plan || [])
    .map((a) => `<div class="card"><strong>${a.action}</strong> → ${a.target}<br/>risk ${a.risk_level} · approval ${a.requires_approval}<br/>${a.reason}</div>`)
    .join("") || "—";
  const evidence = (incident.rca && incident.rca.supporting_evidence) || [];
  els.evidence.innerHTML = evidence.slice(0, 8).map((e) => `<div class="card"><em>${e.kind}</em> · ${e.source}<br/>${e.summary}</div>`).join("") || "—";
  els.history.innerHTML = (incident.historical_hits || []).slice(0, 5).map((h) => {
    const p = h.payload || {};
    return `<div class="card">${p.title || p.text || h.id} · score ${Number(h.score || 0).toFixed(3)}</div>`;
  }).join("") || "—";
  els.graph.textContent = JSON.stringify(incident.graph_snapshot || {}, null, 2);
  els.timeline.innerHTML = (incident.timeline || [])
    .map((ev) => `<li><strong>${ev.node}</strong> — ${ev.message}</li>`)
    .join("");
  const waiting = incident.status === "awaiting_approval" || incident.status === "human_review";
  els.approve.disabled = !waiting;
  els.reject.disabled = !waiting;
  els.retry.disabled = !incident.id;
}

async function loadGraph(id) {
  const g = await json(`/incidents/${id}/graph`);
  els.queryA.textContent = JSON.stringify(g.query_a_world_at_0200 || [], null, 2);
  els.queryB.textContent = JSON.stringify(g.query_b_knowledge_at_0200 || [], null, 2);
}

els.submit.onclick = async () => {
  els.submit.disabled = true;
  els.status.textContent = "running";
  try {
    const incident = await json("/incidents", {
      method: "POST",
      body: JSON.stringify({
        title: els.title.value,
        description: els.description.value,
        occurred_at: els.occurred.value,
        logs: ["Athena QueryTimeout", "DAG sales_daily failed"],
      }),
    });
    render(incident);
    await loadGraph(incident.id);
  } catch (err) {
    els.triage.textContent = String(err);
  } finally {
    els.submit.disabled = false;
  }
};

els.demo.onclick = () => {
  els.title.value = "sales_daily Airflow failure";
  els.occurred.value = "2026-09-27T02:14:00Z";
  els.description.value = "sales_daily failed at 02:14 UTC because Athena timed out and sales_fact_detail was not refreshed.";
};

els.approve.onclick = async () => {
  if (!currentId) return;
  const incident = await json(`/incidents/${currentId}/approve`, {
    method: "POST",
    body: JSON.stringify({ approved_by: "sre-oncall", comment: "Approved simulated restart + rerun" }),
  });
  render(incident);
  await loadGraph(currentId);
};

els.reject.onclick = async () => {
  if (!currentId) return;
  const incident = await json(`/incidents/${currentId}/reject`, {
    method: "POST",
    body: JSON.stringify({ rejected_by: "sre-oncall", comment: "Hold" }),
  });
  render(incident);
};

els.retry.onclick = async () => {
  if (!currentId) return;
  const incident = await json(`/incidents/${currentId}/retry`, { method: "POST" });
  render(incident);
  await loadGraph(currentId);
};

refreshHealth();
setInterval(refreshHealth, 15000);
