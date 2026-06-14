"use client";

import {
  CheckCircle2,
  MessageSquarePlus,
  Plus,
  Send,
  ShieldAlert,
  X,
  XCircle,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Badge, LoadingState } from "@/components/page-state";
import { apiFetch, fetchAll } from "@/lib/api";
import type { Me, Worker } from "@/lib/types";

type Comment = { id: string; author_name?: string; body: string; is_worker_visible: boolean; created_at: string };
type Evidence = { id: string; evidence_type: string; text: string; file?: string; created_at: string };
type Dispute = {
  id: string;
  worker: string;
  worker_name: string;
  worker_code: string;
  dispute_type: string;
  date_reference: string;
  description: string;
  status: string;
  priority: string;
  assigned_to_name?: string;
  raised_via: string;
  sla_due_at: string;
  escalated_at: string | null;
  resolution: string;
  resolved_by_name?: string;
  linked_payroll_line: string | null;
  linked_adjustment: string | null;
  payroll_cycle_name?: string;
  evidence: Evidence[];
  comments: Comment[];
  created_at: string;
};

type PayrollLine = { id: string; cycle_name: string; period_start: string; period_end: string; net_pay: string };
const createRoles = new Set(["supervisor", "operations", "hr", "admin", "owner"]);
const resolverRoles = new Set(["hr", "admin", "owner"]);
const types = ["absent_but_present", "overtime_missing", "wrong_deduction", "salary_not_received", "advance_issue", "wrong_site", "other"];
const priorities = ["low", "normal", "high", "urgent"];

function messageFrom(error: unknown) {
  return error instanceof Error ? error.message : "Request failed.";
}

export default function DisputesPage() {
  const [items, setItems] = useState<Dispute[] | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [payrollLines, setPayrollLines] = useState<PayrollLine[]>([]);
  const [workerId, setWorkerId] = useState("");
  const [selected, setSelected] = useState<Dispute | null>(null);
  const [creating, setCreating] = useState(false);
  const [statusFilter, setStatusFilter] = useState("active");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    try {
      const profile = await apiFetch<Me>("auth/me/");
      const [disputes, workerRows] = await Promise.all([
        fetchAll<Dispute>("disputes/?page_size=200&ordering=-created_at"),
        createRoles.has(profile.role)
          ? fetchAll<Worker>("workers/?page_size=500&status=active")
          : Promise.resolve([]),
      ]);
      setMe(profile);
      setItems(disputes);
      setWorkers(workerRows);
      setSelected((current) =>
        current ? disputes.find((item) => item.id === current.id) ?? null : null,
      );
    } catch (loadError) {
      setError(messageFrom(loadError));
      setItems([]);
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => void load());
  }, [load]);

  function selectWorker(nextWorkerId: string) {
    setWorkerId(nextWorkerId);
    setPayrollLines([]);
    if (!nextWorkerId || !me || !resolverRoles.has(me.role)) return;
    fetchAll<PayrollLine>(`payroll-lines/?worker=${nextWorkerId}&page_size=100`)
      .then(setPayrollLines)
      .catch((requestError) => setError(messageFrom(requestError)));
  }

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (items ?? []).filter((item) => {
      const statusMatches =
        statusFilter === "all" ||
        (statusFilter === "active"
          ? !["resolved", "rejected"].includes(item.status)
          : item.status === statusFilter);
      return statusMatches && (!needle || `${item.worker_name} ${item.worker_code} ${item.description}`.toLowerCase().includes(needle));
    });
  }, [items, query, statusFilter]);

  async function createDispute(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("create");
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      await apiFetch<Dispute>("disputes/", {
        method: "POST",
        body: JSON.stringify({
          worker: form.get("worker"),
          dispute_type: form.get("dispute_type"),
          date_reference: form.get("date_reference"),
          priority: form.get("priority"),
          description: form.get("description"),
          linked_payroll_line: form.get("linked_payroll_line") || null,
        }),
      });
      setCreating(false);
      setWorkerId("");
      setNotice("Dispute opened and routed for review.");
      await load();
    } catch (requestError) {
      setError(messageFrom(requestError));
    } finally {
      setBusy("");
    }
  }

  async function action(path: string, body: object, success: string) {
    if (!selected) return;
    setBusy(path);
    setError("");
    try {
      const updated = await apiFetch<Dispute>(`disputes/${selected.id}/${path}/`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setSelected(updated);
      setNotice(success);
      await load();
    } catch (requestError) {
      setError(messageFrom(requestError));
    } finally {
      setBusy("");
    }
  }

  async function addComment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    setBusy("comment");
    try {
      await apiFetch("dispute-comments/", {
        method: "POST",
        body: JSON.stringify({
          dispute: selected.id,
          body: form.get("body"),
          is_worker_visible: form.get("is_worker_visible") === "on",
        }),
      });
      event.currentTarget.reset();
      setNotice("Case note added.");
      await load();
    } catch (requestError) {
      setError(messageFrom(requestError));
    } finally {
      setBusy("");
    }
  }

  async function addEvidence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    setBusy("evidence");
    try {
      await apiFetch("dispute-evidence/", {
        method: "POST",
        body: JSON.stringify({
          dispute: selected.id,
          evidence_type: "text",
          text: form.get("text"),
        }),
      });
      event.currentTarget.reset();
      setNotice("Evidence note attached.");
      await load();
    } catch (requestError) {
      setError(messageFrom(requestError));
    } finally {
      setBusy("");
    }
  }

  if (!items || !me) return <LoadingState label="Loading dispute workspace..." />;
  const activeCount = items.filter((item) => !["resolved", "rejected"].includes(item.status)).length;
  const overdueCount = items.filter((item) => !["resolved", "rejected"].includes(item.status) && new Date(item.sla_due_at) < new Date()).length;
  const awaitingHr = items.filter((item) => item.status === "hr_review").length;
  const closed = selected && ["resolved", "rejected"].includes(selected.status);

  return (
    <>
      <header className="page-head">
        <div><p className="eyebrow">Worker issue resolution</p><h1>Disputes</h1><p>Investigate attendance and wage concerns with evidence, SLA, and adjustment trails.</p></div>
        {createRoles.has(me.role) && <button className="button" onClick={() => setCreating(true)}><Plus size={17} /> Open dispute</button>}
      </header>
      {error && <p className="sync-banner payroll-error">{error}</p>}
      {notice && <p className="sync-banner payroll-notice">{notice}</p>}
      <section className="grid stats">
        <article className="card stat"><div className="label">Open cases</div><div className="value">{activeCount}</div><div className="hint">Across supervisor and HR review</div></article>
        <article className="card stat"><div className="label">Awaiting HR</div><div className="value">{awaitingHr}</div><div className="hint">Ready for final investigation</div></article>
        <article className="card stat"><div className="label">SLA overdue</div><div className="value">{overdueCount}</div><div className="hint">Open beyond their due time</div></article>
        <article className="card stat"><div className="label">Resolved</div><div className="value">{items.filter((item) => item.status === "resolved").length}</div><div className="hint">Closed with a recorded outcome</div></article>
      </section>
      <div className="toolbar">
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search worker, code, or issue" />
        <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
          <option value="active">Active cases</option><option value="all">All cases</option>
          {["supervisor_review", "hr_review", "resolved", "rejected"].map((status) => <option key={status}>{status}</option>)}
        </select>
      </div>
      <div className="table-wrap"><table><thead><tr><th>Worker</th><th>Issue</th><th>Reference date</th><th>Priority</th><th>Owner / SLA</th><th>Status</th><th>Action</th></tr></thead><tbody>
        {filtered.map((item) => {
          const overdue = !["resolved", "rejected"].includes(item.status) && new Date(item.sla_due_at) < new Date();
          return <tr key={item.id}><td><button className="table-link" onClick={() => setSelected(item)}>{item.worker_name}</button><br /><span className="muted">{item.worker_code}</span></td><td>{item.dispute_type.replaceAll("_", " ")}<br /><span className="muted">{item.description}</span></td><td>{item.date_reference}</td><td><Badge value={item.priority} /></td><td>{item.assigned_to_name || "HR queue"}<br /><span className={overdue ? "sla-overdue" : "muted"}>{overdue ? "Overdue · " : ""}{new Date(item.sla_due_at).toLocaleString()}</span></td><td><Badge value={item.status} /></td><td><button className="button secondary" onClick={() => setSelected(item)}>Review</button></td></tr>;
        })}
      </tbody></table>{!filtered.length && <div className="empty">No disputes match these filters.</div>}</div>

      {creating && <div className="modal-backdrop"><form className="review-panel" onSubmit={createDispute}>
        <div className="review-head"><div><p className="eyebrow">New case</p><h2>Open a worker dispute</h2><p>Route the issue to the worker&apos;s supervisor, or directly to HR when none is assigned.</p></div><button type="button" className="icon-button" onClick={() => setCreating(false)}><X size={20} /></button></div>
        <div className="worker-form-grid" style={{ marginTop: "1rem" }}>
          <div className="field span-2"><label>Worker</label><select name="worker" required value={workerId} onChange={(event) => selectWorker(event.target.value)}><option value="">Select worker</option>{workers.map((worker) => <option key={worker.id} value={worker.id}>{worker.worker_code} · {worker.full_name}</option>)}</select></div>
          <div className="field"><label>Issue type</label><select name="dispute_type" required>{types.map((type) => <option key={type} value={type}>{type.replaceAll("_", " ")}</option>)}</select></div>
          <div className="field"><label>Reference date</label><input name="date_reference" type="date" defaultValue={new Date().toISOString().slice(0, 10)} required /></div>
          <div className="field"><label>Priority</label><select name="priority" defaultValue="normal">{priorities.map((priority) => <option key={priority}>{priority}</option>)}</select></div>
          <div className="field span-2"><label>Related payroll line (optional)</label><select name="linked_payroll_line"><option value="">No payroll line</option>{payrollLines.map((line) => <option key={line.id} value={line.id}>{line.cycle_name} · AED {line.net_pay}</option>)}</select></div>
          <div className="field span-2"><label>What happened?</label><textarea name="description" rows={4} minLength={5} required /></div>
        </div>
        <div className="decision-actions"><button className="button" disabled={busy === "create"}>Open dispute</button><button type="button" className="button secondary" onClick={() => setCreating(false)}>Cancel</button></div>
      </form></div>}

      {selected && <div className="modal-backdrop"><section className="review-panel dispute-panel">
        <div className="review-head"><div><p className="eyebrow">{selected.dispute_type.replaceAll("_", " ")}</p><h2>{selected.worker_name}</h2><p>{selected.worker_code} · {selected.date_reference} · raised through {selected.raised_via.replaceAll("_", " ")}</p></div><button className="icon-button" onClick={() => setSelected(null)}><X size={20} /></button></div>
        <div className="advance-summary-grid"><div><span>Status</span><Badge value={selected.status} /></div><div><span>Priority</span><Badge value={selected.priority} /></div><div><span>Assigned to</span><strong>{selected.assigned_to_name || "HR queue"}</strong></div><div><span>SLA due</span><strong>{new Date(selected.sla_due_at).toLocaleString()}</strong></div></div>
        <div className="case-note"><strong>Worker statement</strong><p>{selected.description}</p></div>
        {selected.payroll_cycle_name && <div className="review-summary"><ShieldAlert size={18} /><span>Linked to payroll cycle <strong>{selected.payroll_cycle_name}</strong>{selected.linked_adjustment ? " · adjustment created" : ""}</span></div>}
        {selected.resolution && <div className="case-note"><strong>{selected.status === "rejected" ? "Rejection reason" : "Resolution"}</strong><p>{selected.resolution}</p><span className="muted">Closed by {selected.resolved_by_name || "HR"}</span></div>}

        <section className="case-section"><h3>Evidence</h3>{selected.evidence.length ? selected.evidence.map((item) => <article className="case-entry" key={item.id}><strong>{item.evidence_type}</strong><p>{item.text || item.file}</p><span>{new Date(item.created_at).toLocaleString()}</span></article>) : <p className="muted">No evidence attached yet.</p>}
          {!closed && <form onSubmit={addEvidence}><div className="field"><label>Add evidence note</label><textarea name="text" rows={2} minLength={3} required /></div><button className="button secondary" disabled={busy === "evidence"}><Plus size={15} /> Attach note</button></form>}
        </section>
        <section className="case-section"><h3>Case discussion</h3>{selected.comments.map((comment) => <article className="case-entry" key={comment.id}><strong>{comment.author_name || "Worker portal"}</strong><p>{comment.body}</p><span>{new Date(comment.created_at).toLocaleString()} · {comment.is_worker_visible ? "worker visible" : "internal"}</span></article>)}
          <form onSubmit={addComment}><div className="field"><label>Add case note</label><textarea name="body" rows={2} minLength={2} required /></div><label className="role-check"><input name="is_worker_visible" type="checkbox" defaultChecked /> Visible to worker</label><button className="button secondary" disabled={busy === "comment"} style={{ marginTop: ".7rem" }}><MessageSquarePlus size={15} /> Add note</button></form>
        </section>
        {!closed && selected.status !== "hr_review" && createRoles.has(me.role) && <button className="button secondary" disabled={busy === "escalate"} onClick={() => void action("escalate", {}, "Dispute escalated to HR.")}><Send size={16} /> Escalate to HR</button>}
        {!closed && resolverRoles.has(me.role) && <form className="case-resolution" onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); void action("resolve", { resolution: form.get("resolution"), adjustment_amount: form.get("adjustment_amount") || undefined }, "Dispute resolved."); }}>
          <h3>Final decision</h3><div className="field"><label>Resolution or rejection reason</label><textarea name="resolution" rows={3} minLength={3} required /></div>
          {selected.linked_payroll_line && <div className="field"><label>Payroll adjustment AED (optional, negative for a deduction)</label><input name="adjustment_amount" type="number" step="0.01" /></div>}
          <div className="decision-actions"><button className="button" disabled={busy === "resolve"}><CheckCircle2 size={16} /> Resolve</button><button type="button" className="button danger" disabled={busy === "reject"} onClick={(event) => { const form = event.currentTarget.closest("form"); const reason = form?.querySelector<HTMLTextAreaElement>("[name=resolution]")?.value || ""; void action("reject", { reason }, "Dispute rejected."); }}><XCircle size={16} /> Reject claim</button></div>
        </form>}
      </section></div>}
    </>
  );
}
