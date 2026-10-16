import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { getMissionData } from "./api";
import "./styles.css";

const Panel = ({ title, action, children }) => (
  <section className="panel">
    <header><b>{title}</b><span>{action}</span></header>
    {children}
  </section>
);

function App() {
  const [data, setData] = useState();
  const [filter, setFilter] = useState("ALL");
  const [role, setRole] = useState("Commander");
  const [scenario, setScenario] = useState("flood");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState();
  const [busy, setBusy] = useState(false);

  const refresh = () => getMissionData().then(setData);
  useEffect(refresh, []);

  async function runScenario() {
    setBusy(true);
    try {
      const response = await fetch(`/api/v1/scenarios/${scenario}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ count: 14, seed: 7, plant_anomalies: ["all"] }),
      });
      if (!response.ok) throw new Error("Scenario request failed");
      await refresh();
    } catch (error) {
      setAnswer({ answer: error.message });
    } finally {
      setBusy(false);
    }
  }

  async function askAssistant(event) {
    event.preventDefault();
    if (!question.trim()) return;
    const response = await fetch("/api/v1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    setAnswer(await response.json());
  }

  if (!data) return <main className="loading">Connecting to SENTINAL…<small>Offline cache ready</small></main>;
  const alerts = data.alerts.filter((alert) => filter === "ALL" || alert[0] === filter);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand"><b>SENTINAL</b><span>MISSION CONTROL</span></div>
        <div className="status">● LIVE · SYNTHETIC FEED <select value={role} onChange={(event) => setRole(event.target.value)} aria-label="Role"><option>Commander</option><option>Analyst</option><option>Observer</option></select></div>
      </header>
      <nav><button className="active">◈ Overview</button><button>⌁ Assets</button><button>◇ Scenarios</button><button>▤ Reports</button></nav>
      <main>
        <section className="hero"><div><p className="eyebrow">ORBITAL DEFENSE NETWORK / SECTOR 07</p><h1>Situation overview</h1><p className="muted">Current in-memory synthetic state · {role}</p></div><button className="outline" onClick={refresh}>↻ Refresh</button></section>
        <div className="grid top">
          <Panel title="THREAT MAP" action="Expand"><div className="map"><i className="orbit" /><span className="maplabel">SYNTHETIC MAP DATA<br /><small>Leaflet-ready projection</small></span></div></Panel>
          <Panel title="MISSION RISK"><div className="risk"><div className="gauge"><strong>{data.risk}</strong><small>/ 100</small></div><div><b className="red">{data.risk >= 80 ? "CRITICAL" : data.risk >= 60 ? "ELEVATED" : "LOW"}</b><p className="muted">Latest stored scenario</p></div></div><div className="bar"><i style={{ width: `${data.risk}%` }} /></div><div className="legend"><span>LOW 0</span><span>CRITICAL 100</span></div></Panel>
          <Panel title="ALERT FEED" action={<span className="filters">{["ALL", "CRITICAL", "HIGH", "WATCH"].map((value) => <button className={filter === value ? "sel" : ""} onClick={() => setFilter(value)} key={value}>{value}</button>)}</span>}><div className="alerts">{alerts.map((alert, index) => <article key={`${alert[1]}-${index}`}><b className={`tag ${alert[0].toLowerCase()}`}>{alert[0]}</b><span><strong>{alert[1]}</strong><small>{alert[2]}</small></span>›</article>)}</div></Panel>
        </div>
        <div className="grid bottom">
          <Panel title="WHY THIS SCORE"><p className="explain">Run a synthetic scenario to create a risk explanation and alert. All results remain local and deterministic.</p><div className="chips"><span>EXPLAINABLE</span><span>SYNTHETIC</span><span>OFFLINE</span></div></Panel>
          <Panel title="ASSET RANKING"><table><thead><tr><th>ASSET</th><th>RISK</th><th>STATUS</th></tr></thead><tbody>{alerts.map((alert, index) => <tr key={`${alert[1]}-row-${index}`}><td>{alert[1]}</td><td className="score">{data.risk}</td><td>{alert[0]}</td></tr>)}</tbody></table></Panel>
          <Panel title="TELEMETRY STREAM"><div className="telemetry">{data.telemetry.map((item) => <code key={item}>{item}</code>)}</div><div className="healthy">● FEED HEALTHY · LOCAL STATE</div></Panel>
        </div>
        <section className="launch"><b>SCENARIO LAUNCHER</b><span className="muted">Test response against synthetic data</span><select value={scenario} onChange={(event) => setScenario(event.target.value)} aria-label="Scenario"><option value="flood">Flood</option><option value="wildfire">Wildfire</option><option value="satellite_fault">Satellite fault</option><option value="cyber_attack">Cyber attack</option></select><button className="primary" onClick={runScenario} disabled={busy}>{busy ? "Running…" : "▶ Run scenario"}</button></section>
        <section className="chat"><b>✦ Mission assistant</b><span className="muted">Ask about detected changes, hotspots, or flag rationale</span><form onSubmit={askAssistant}><input aria-label="Message assistant" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="e.g. What changed?" /><button className="primary">Send ↑</button></form>{answer && <p className="muted">{answer.answer}</p>}</section>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
