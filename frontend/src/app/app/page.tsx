"use client";

import { AlertTriangle, ArrowUpRight, CheckCircle2, Clock3 } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, ErrorState, LoadingState } from "@/components/page-state";
import { fetchAll } from "@/lib/api";
import type { Attendance, Worker } from "@/lib/types";

type Alert = { id: string; title: string; severity: string; status: string; description: string };
type Dispute = { id: string; worker_name: string; dispute_type: string; status: string; sla_due_at: string };

export default function OverviewPage() {
  const [data, setData] = useState<{ workers: Worker[]; attendance: Attendance[]; alerts: Alert[]; disputes: Dispute[] } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      fetchAll<Worker>("workers/?status=active&page_size=200"),
      fetchAll<Attendance>(`attendance/?work_date=${new Date().toISOString().slice(0, 10)}&page_size=200`),
      fetchAll<Alert>("compliance-alerts/?status=open&page_size=10"),
      fetchAll<Dispute>("disputes/?page_size=10"),
    ]).then(([workers, attendance, alerts, disputes]) => setData({ workers, attendance, alerts, disputes })).catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!data) return <LoadingState />;
  const present = new Set(data.attendance.map((item) => item.worker)).size;
  const exceptions = data.attendance.filter((item) => item.flags.length).length;

  return (
    <>
      <header className="page-head">
        <div><p className="eyebrow">Live control room</p><h1>Today at a glance</h1><p>Attendance, payroll risk, and worker issues in one operational view.</p></div>
        <button className="button">Review payroll readiness <ArrowUpRight size={17} /></button>
      </header>
      <section className="grid stats">
        <article className="card stat"><div className="label">Active workers</div><div className="value">{data.workers.length}</div><div className="hint">Across accessible sites</div></article>
        <article className="card stat"><div className="label">Present today</div><div className="value">{present}</div><div className="hint">{data.workers.length ? Math.round(present / data.workers.length * 100) : 0}% attendance captured</div></article>
        <article className="card stat"><div className="label">Exceptions</div><div className="value">{exceptions}</div><div className="hint">Need review before approval</div></article>
        <article className="card stat"><div className="label">Compliance alerts</div><div className="value">{data.alerts.length}</div><div className="hint">Open items in your scope</div></article>
      </section>
      <section className="grid two-col">
        <article className="card">
          <div className="page-head" style={{ marginBottom: "1rem" }}><div><h2>Open compliance items</h2><p>Resolve the highest-risk controls first.</p></div><AlertTriangle size={22} /></div>
          {data.alerts.length ? data.alerts.map((alert) => (
            <div key={alert.id} style={{ padding: ".85rem 0", borderTop: "1px solid var(--line)", display: "flex", justifyContent: "space-between", gap: "1rem" }}>
              <div><strong>{alert.title}</strong><p style={{ color: "var(--muted)", fontSize: ".8rem", margin: ".2rem 0 0" }}>{alert.description}</p></div><Badge value={alert.severity} />
            </div>
          )) : <div className="empty"><CheckCircle2 size={25} /><p>No open compliance alerts.</p></div>}
        </article>
        <article className="card">
          <div className="page-head" style={{ marginBottom: "1rem" }}><div><h2>Worker disputes</h2><p>Tracked with a visible SLA.</p></div><Clock3 size={22} /></div>
          {data.disputes.length ? data.disputes.map((dispute) => (
            <div key={dispute.id} style={{ padding: ".85rem 0", borderTop: "1px solid var(--line)", display: "flex", justifyContent: "space-between", gap: "1rem" }}>
              <div><strong>{dispute.worker_name}</strong><p style={{ color: "var(--muted)", fontSize: ".8rem", margin: ".2rem 0 0" }}>{dispute.dispute_type.replaceAll("_", " ")}</p></div><Badge value={dispute.status} />
            </div>
          )) : <div className="empty">No disputes in the current queue.</div>}
        </article>
      </section>
    </>
  );
}

