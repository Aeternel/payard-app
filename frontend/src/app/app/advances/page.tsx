"use client";

import { useEffect, useState } from "react";
import { Badge, LoadingState } from "@/components/page-state";
import { fetchAll } from "@/lib/api";

type Advance = { id: string; worker_name: string; requested_amount: string; approved_amount: string; status: string; created_at: string; deduction_cycle: string | null };
export default function AdvancesPage() {
  const [items, setItems] = useState<Advance[] | null>(null);
  useEffect(() => { fetchAll<Advance>("advances/?page_size=100").then(setItems); }, []);
  if (!items) return <LoadingState label="Loading advance ledger..." />;
  return <><header className="page-head"><div><p className="eyebrow">Transparent deductions</p><h1>Advance ledger</h1><p>Eligibility, approvals, disbursement references, and payroll reconciliation.</p></div></header><div className="table-wrap"><table><thead><tr><th>Worker</th><th>Requested</th><th>Approved</th><th>Requested at</th><th>Status</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><strong>{item.worker_name}</strong></td><td>AED {item.requested_amount}</td><td>AED {item.approved_amount}</td><td>{new Date(item.created_at).toLocaleDateString()}</td><td><Badge value={item.status} /></td></tr>)}</tbody></table></div></>;
}

