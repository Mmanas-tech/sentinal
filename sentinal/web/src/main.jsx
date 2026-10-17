import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "./styles.css";

const scenarios = [
  ["flood", "Flood"],
  ["wildfire", "Wildfire"],
  ["satellite_fault", "Satellite fault"],
  ["cyber_attack", "Cyber attack"],
];

const demoFallback = {
  risk: 0,
  alerts: [],
  telemetry: ["API unavailable", "No live or file-based source connected"],
  diagnostics: {
    status: "DEMO",
    source: "offline-fallback",
    provenance: "local-ui-fallback",
    last_successful_ingestion: null,
    errors: ["backend unavailable"],
  },
};

const Panel = ({ title, action, children }) => (
  <section className="panel">
    <header><b>{title}</b><span>{action}</span></header>
    {children}
  </section>
);

function riskLevel(score = 0) {
  return score >= 80 ? "CRITICAL" : score >= 60 ? "HIGH" : score >= 30 ? "MEDIUM" : "LOW";
}

function App() {
  const [mission, setMission] = useState();
  const [assets, setAssets] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [events, setEvents] = useState([]);
  const [filter, setFilter] = useState("ALL");
  const [scenario, setScenario] = useState("flood");
  const [runningScenario, setRunningScenario] = useState();
  const [selectedAlert, setSelectedAlert] = useState();
  const [connection, setConnection] = useState("connecting");
  const [mapError, setMapError] = useState();
  const [dataError, setDataError] = useState();
  const mapElement = useRef();
  const mapRef = useRef();
  const layersRef = useRef(L.layerGroup());

  async function refresh() {
    const [missionResponse, assetsResponse, alertsResponse, satelliteResponse] = await Promise.all([
      fetch("/api/mission"),
      fetch("/api/v1/risk/assets"),
      fetch("/api/v1/alerts"),
      fetch("/api/v1/satellite/query?limit=500"),
    ]);
    if (!missionResponse.ok || !assetsResponse.ok || !alertsResponse.ok) throw new Error("Dashboard data unavailable");
    setMission(await missionResponse.json());
    setDataError(undefined);
    setAssets((await assetsResponse.json()).items || []);
    setAlerts((await alertsResponse.json()).items || []);
    if (satelliteResponse.ok) setEvents((await satelliteResponse.json()).items || []);
  }

  useEffect(() => {
    refresh().catch(() => {
      setMission(demoFallback);
      setDataError("Dashboard data unavailable — showing DEMO fallback");
      setConnection("reconnecting");
    });
  }, []);

  useEffect(() => {
    let socket;
    let retry;
    let stopped = false;
    const connect = () => {
      setConnection("connecting");
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${protocol}://${window.location.host}/ws/stream`);
      socket.onopen = () => setConnection("live");
      socket.onmessage = (message) => {
        const payload = JSON.parse(message.data);
        if (payload.type === "status") setMission((current) => current ? {...current, diagnostics: payload.data} : current);
        if (payload.type === "event") {
          setEvents((current) => [...current.slice(-499), payload.data]);
          refresh().catch(() => setMapError("Live refresh failed"));
        }
      };
      socket.onclose = () => {
        if (!stopped) {
          setConnection("reconnecting");
          retry = window.setTimeout(connect, 1500);
        }
      };
      socket.onerror = () => socket.close();
    };
    connect();
    return () => {
      stopped = true;
      window.clearTimeout(retry);
      socket?.close();
    };
  }, []);

  useEffect(() => {
    if (!mapElement.current || mapRef.current) return;
    const map = L.map(mapElement.current).setView([51.05, 13.75], 12);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);
    layersRef.current.addTo(map);
    mapRef.current = map;
    return () => map.remove();
  }, []);

  const assetRows = useMemo(() => {
    const byAsset = new Map(alerts.map((alert) => [alert.asset_id, alert]));
    return assets.map((asset) => {
      const alert = byAsset.get(asset.id);
      return {
        ...asset,
        score: Number(asset.risk_score ?? alert?.risk_score ?? 0),
        level: asset.risk_level || riskLevel(Number(asset.risk_score ?? alert?.risk_score ?? 0)),
        status: asset.alert_status || alert?.status || "No alert",
      };
    }).sort((left, right) => right.score - left.score);
  }, [assets, alerts]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    layersRef.current.clearLayers();
    const bounds = [];
    assetRows.forEach((asset) => {
      if (!Number.isFinite(asset.lat) || !Number.isFinite(asset.lon)) return;
      const color = asset.level === "CRITICAL" ? "#ef4444" : asset.level === "HIGH" ? "#f59e0b" : asset.level === "MEDIUM" ? "#eab308" : "#22c55e";
      const marker = L.circleMarker([asset.lat, asset.lon], { radius: 9, color, fillColor: color, fillOpacity: 0.85 });
      marker.bindPopup(`<strong>${asset.name}</strong><br/>Risk: ${asset.score.toFixed(1)}<br/>Status: ${asset.status}`);
      marker.addTo(layersRef.current);
      bounds.push([asset.lat, asset.lon]);
    });
    events.flatMap((event) => event.payload?.hotspots || []).forEach((hotspot) => {
      const point = hotspot.center || hotspot.location;
      if (!point || !Number.isFinite(point.lat) || !Number.isFinite(point.lon)) return;
      L.circleMarker([point.lat, point.lon], { radius: 6, color: "#f97316", fillColor: "#fb923c", fillOpacity: 0.75 })
        .bindPopup(`<strong>${hotspot.region_id || "Hotspot"}</strong><br/>Severity: ${hotspot.severity ?? "n/a"}`)
        .addTo(layersRef.current);
      bounds.push([point.lat, point.lon]);
    });
    if (bounds.length) map.fitBounds(bounds, { padding: [20, 20], maxZoom: 14 });
  }, [assetRows, events]);

  async function runScenario(name = scenario) {
    setRunningScenario(name);
    try {
      const response = await fetch(`/api/v1/scenarios/${name}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ count: 14, seed: 7, plant_anomalies: ["all"] }),
      });
      if (!response.ok) throw new Error("Scenario request failed");
      await refresh();
    } catch (error) {
      setMapError(error.message);
    } finally {
      setRunningScenario(undefined);
    }
  }

  async function inspectAlert(alert) {
    const response = await fetch(`/api/v1/alerts/${alert.id}/explanation`);
    if (response.ok) setSelectedAlert(await response.json());
  }

  async function updateAlert(alert, status) {
    const response = await fetch(`/api/v1/alerts/${alert.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (response.ok) await refresh();
  }

  if (!mission) return <main className="loading">{dataError || "Connecting to SENTINAL…"}</main>;
  const visibleAlerts = alerts.filter((alert) => filter === "ALL" || alert.level.toUpperCase() === filter);
  const currentRisk = Number(mission.risk || 0);

  return (
    <div className="app">
       <header className="topbar">
         <div className="brand"><b>SENTINAL</b><span>MISSION CONTROL</span></div>
         <div className={`status ${connection}`}>● {mission.diagnostics?.status || (connection === "live" ? "LIVE" : connection === "reconnecting" ? "DEGRADED" : "OFFLINE")} · {mission.diagnostics?.source || "DEMO"}</div>
      </header>
      {(connection === "reconnecting" || dataError) && <div className="reconnect-banner">{dataError || "Live stream disconnected. Reconnecting…"}</div>}
      <main>
         <section className="hero"><div><p className="eyebrow">ORBITAL DEFENSE NETWORK / SECTOR 07</p><h1>Situation overview</h1><p className="muted">{mission.diagnostics?.status || "DEMO"} · Source: {mission.diagnostics?.provenance || "synthetic offline fallback"}{mission.diagnostics?.last_successful_ingestion ? ` · Updated ${mission.diagnostics.last_successful_ingestion}` : ""}</p></div><button className="outline" onClick={() => refresh()}>↻ Refresh</button></section>
        <div className="grid top">
          <Panel title="ASSET MAP" action={<span className="map-note">OpenStreetMap</span>}><div ref={mapElement} className="map" />{mapError && <p className="muted">{mapError}</p>}<div className="map-legend"><span><i className="legend-dot low" />Low</span><span><i className="legend-dot high" />High</span><span><i className="legend-dot critical" />Critical</span><span><i className="legend-dot hotspot" />Hotspot</span></div></Panel>
          <Panel title="MISSION RISK"><div className="risk"><div className="gauge"><strong>{currentRisk}</strong><small>/ 100</small></div><div><b className={`level ${riskLevel(currentRisk).toLowerCase()}`}>{riskLevel(currentRisk)}</b><p className="muted">Latest backend risk</p></div></div><div className="bar"><i style={{ width: `${Math.min(100, currentRisk)}%` }} /></div><div className="legend"><span>LOW 0</span><span>CRITICAL 100</span></div></Panel>
          <Panel title="ALERT FEED" action={<span className="filters">{["ALL", "CRITICAL", "HIGH", "MEDIUM"].map((value) => <button className={filter === value ? "sel" : ""} onClick={() => setFilter(value)} key={value}>{value}</button>)}</span>}>
            <div className="alerts">{visibleAlerts.length ? visibleAlerts.map((alert) => <article key={alert.id} onClick={() => inspectAlert(alert)}><b className={`tag ${alert.level}`}>{alert.level.toUpperCase()}</b><span><strong>{alert.asset_id}</strong><small>{alert.status} · {Number(alert.risk_score).toFixed(1)}</small></span><button className="outline" onClick={(event) => { event.stopPropagation(); inspectAlert(alert); }}>Inspect</button>{alert.status === "New" && <button className="outline" onClick={(event) => { event.stopPropagation(); updateAlert(alert, "Acknowledged"); }}>Acknowledge</button>}</article>) : <p className="muted">No alerts match this filter.</p>}</div>
            {selectedAlert && <div className="explain"><strong>{selectedAlert.what || "Alert explanation"}</strong><p>{(selectedAlert.why || []).join("; ")}</p><p className="muted">Evidence: {(selectedAlert.evidence || []).map((item) => item.ref).join(", ") || "none"}</p><a href={`/api/v1/reports/${selectedAlert.alert_id}`} target="_blank" rel="noreferrer">Open PDF report</a></div>}
          </Panel>
        </div>
        <div className="grid bottom">
          <Panel title="ASSET RANKING"><table><thead><tr><th>ASSET</th><th>RISK</th><th>STATUS</th></tr></thead><tbody>{assetRows.map((asset) => <tr key={asset.id}><td>{asset.name}</td><td className={`score ${asset.level.toLowerCase()}`}>{asset.score.toFixed(1)}</td><td>{asset.status}</td></tr>)}</tbody></table></Panel>
          <Panel title="TELEMETRY STREAM"><div className="telemetry">{mission.telemetry.map((item) => <code key={item}>{item}</code>)}</div><div className={`healthy ${connection !== "live" ? "warning" : ""}`}>● {connection === "live" ? "LIVE BACKEND STREAM" : "STREAM RECONNECTING"}</div></Panel>
          <Panel title="SCENARIOS"><div className="scenario-grid">{scenarios.map(([name, label]) => <button className="primary" key={name} disabled={Boolean(runningScenario)} onClick={() => runScenario(name)}>{runningScenario === name ? "Running…" : label}</button>)}</div>{runningScenario && <span className="scenario-badge">synthetic scenario: {runningScenario}</span>}</Panel>
        </div>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
