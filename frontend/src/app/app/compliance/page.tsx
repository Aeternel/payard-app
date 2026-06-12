"use client";

import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, LoadingState } from "@/components/page-state";
import { apiFetch, fetchAll } from "@/lib/api";

type Alert = { id: string; title: string; description: string; alert_type: string; severity: string; status: string; occurrence_date: string };
export default function CompliancePage() {
  const [items, setItems] = useState<Alert[] | null>(null);
  const load = () => fetchAll<Alert>("compliance-alerts/?page_size=100").then(setItems);
  useEffect(() => {
    void load();
  }, []);
  async function scan() { await apiFetch("compliance-alerts/scan/", { method: "POST", body: "{}" }); }
  if (!items) return <LoadingState label="Loading compliance controls..." />;
  return <><header className="page-head"><div><p className="eyebrow">Compliance-aware controls</p><h1>Alerts</h1><p>Operational signals for UAE work-hour, heat, consent, and payroll risks. Legal validation remains required before launch.</p></div><button className="button secondary" onClick={scan}><RefreshCw size={17} /> Run scan</button></header><div className="table-wrap"><table><thead><tr><th>Alert</th><th>Type</th><th>Date</th><th>Severity</th><th>Status</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><strong>{item.title}</strong><br /><span style={{ color: "var(--muted)" }}>{item.description}</span></td><td>{item.alert_type.replaceAll("_", " ")}</td><td>{item.occurrence_date}</td><td><Badge value={item.severity} /></td><td><Badge value={item.status} /></td></tr>)}</tbody></table></div></>;
}
