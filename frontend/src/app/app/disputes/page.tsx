"use client";

import { useEffect, useState } from "react";
import { Badge, LoadingState } from "@/components/page-state";
import { fetchAll } from "@/lib/api";

type Dispute = { id: string; worker_name: string; dispute_type: string; date_reference: string; description: string; status: string; priority: string; sla_due_at: string };
export default function DisputesPage() {
  const [items, setItems] = useState<Dispute[] | null>(null);
  useEffect(() => { fetchAll<Dispute>("disputes/?page_size=100").then(setItems); }, []);
  if (!items) return <LoadingState label="Loading dispute queue..." />;
  return <><header className="page-head"><div><p className="eyebrow">Worker issue register</p><h1>Disputes</h1><p>Evidence, routing, SLA, and approved adjustment trails.</p></div></header><div className="table-wrap"><table><thead><tr><th>Worker</th><th>Issue</th><th>Date</th><th>Priority</th><th>SLA due</th><th>Status</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><strong>{item.worker_name}</strong></td><td>{item.dispute_type.replaceAll("_", " ")}<br /><span style={{ color: "var(--muted)" }}>{item.description}</span></td><td>{item.date_reference}</td><td><Badge value={item.priority} /></td><td>{new Date(item.sla_due_at).toLocaleString()}</td><td><Badge value={item.status} /></td></tr>)}</tbody></table></div></>;
}

