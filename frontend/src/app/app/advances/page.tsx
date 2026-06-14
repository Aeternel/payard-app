"use client";

import {
  CheckCircle2,
  HandCoins,
  Landmark,
  Plus,
  Settings2,
  X,
  XCircle,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Badge, LoadingState } from "@/components/page-state";
import { apiFetch, fetchAll } from "@/lib/api";
import type { Me, Worker } from "@/lib/types";

type Advance = {
  id: string;
  worker: string;
  worker_name: string;
  worker_code: string;
  requested_amount: string;
  available_limit_snapshot: string;
  available_limit: string;
  approved_amount: string;
  acknowledgement_text: string;
  status: string;
  requested_via: string;
  requested_by_name?: string;
  approved_by_name?: string;
  approved_at: string | null;
  decision_reason: string;
  disbursed_at: string | null;
  deduction_cycle: string | null;
  deduction_cycle_name?: string;
  created_at: string;
};

type Policy = {
  id: string;
  enabled: boolean;
  minimum_service_days: number;
  max_earned_wage_percentage: string;
  max_requests_per_cycle: number;
  minimum_amount: string;
  maximum_amount: string | null;
  approver_roles: string[];
  acknowledgement_text: string;
};

type Cycle = { id: string; name: string; status: string; period_start: string; period_end: string };
type Eligibility = {
  available_limit: string;
  minimum_amount: string;
  acknowledgement_text: string;
  enabled: boolean;
};

const requestRoles = new Set(["hr", "admin", "owner"]);
const disbursementRoles = new Set(["finance", "admin", "owner"]);
const policyRoles = new Set(["finance", "admin", "owner"]);
const roleOptions = ["hr", "payroll", "finance", "admin", "owner"];

function messageFrom(error: unknown) {
  if (!(error instanceof Error)) return "Request failed.";
  return error.message || "Request failed.";
}

export default function AdvancesPage() {
  const [items, setItems] = useState<Advance[] | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [cycles, setCycles] = useState<Cycle[]>([]);
  const [selected, setSelected] = useState<Advance | null>(null);
  const [modal, setModal] = useState<"create" | "policy" | null>(null);
  const [workerId, setWorkerId] = useState("");
  const [eligibility, setEligibility] = useState<Eligibility | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    try {
      const profile = await apiFetch<Me>("auth/me/");
      const [advances, advancePolicy, workerRows, cycleRows] = await Promise.all([
        fetchAll<Advance>("advances/?page_size=200&ordering=-created_at"),
        apiFetch<Policy>("advance-policy/"),
        requestRoles.has(profile.role)
          ? fetchAll<Worker>("workers/?page_size=500&status=active")
          : Promise.resolve([]),
        disbursementRoles.has(profile.role)
          ? fetchAll<Cycle>("payroll-cycles/?page_size=100")
          : Promise.resolve([]),
      ]);
      setMe(profile);
      setItems(advances);
      setPolicy(advancePolicy);
      setWorkers(workerRows);
      setCycles(cycleRows);
      setSelected((current) =>
        current ? advances.find((item) => item.id === current.id) ?? null : null,
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
    setEligibility(null);
    if (!nextWorkerId) return;
    apiFetch<Eligibility>(`advances/eligibility/?worker=${nextWorkerId}`)
      .then(setEligibility)
      .catch((requestError) => setError(messageFrom(requestError)));
  }

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (items ?? []).filter(
      (item) =>
        (statusFilter === "all" || item.status === statusFilter) &&
        (!needle ||
          item.worker_name.toLowerCase().includes(needle) ||
          item.worker_code.toLowerCase().includes(needle)),
    );
  }, [items, query, statusFilter]);

  async function createRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("create");
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      await apiFetch<Advance>("advances/", {
        method: "POST",
        body: JSON.stringify({
          worker: form.get("worker"),
          requested_amount: form.get("amount"),
          acknowledgement: form.get("acknowledgement") === "on",
        }),
      });
      setModal(null);
      setWorkerId("");
      setNotice("Advance request created and sent for approval.");
      await load();
    } catch (requestError) {
      setError(messageFrom(requestError));
    } finally {
      setBusy("");
    }
  }

  async function decide(approve: boolean, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    setBusy("decision");
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const updated = await apiFetch<Advance>(`advances/${selected.id}/decide/`, {
        method: "POST",
        body: JSON.stringify({
          approve,
          amount: form.get("amount"),
          reason: form.get("reason"),
        }),
      });
      setSelected(updated);
      setNotice(approve ? "Advance approved." : "Advance rejected.");
      await load();
    } catch (requestError) {
      setError(messageFrom(requestError));
    } finally {
      setBusy("");
    }
  }

  async function disburse(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    setBusy("disburse");
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const updated = await apiFetch<Advance>(`advances/${selected.id}/disburse/`, {
        method: "POST",
        body: JSON.stringify({
          reference: form.get("reference"),
          deduction_cycle: form.get("deduction_cycle"),
        }),
      });
      setSelected(updated);
      setNotice("Disbursement recorded and scheduled for payroll deduction.");
      await load();
    } catch (requestError) {
      setError(messageFrom(requestError));
    } finally {
      setBusy("");
    }
  }

  async function cancelRequest() {
    if (!selected) return;
    setBusy("cancel");
    setError("");
    try {
      const updated = await apiFetch<Advance>(`advances/${selected.id}/cancel/`, {
        method: "POST",
      });
      setSelected(updated);
      setNotice("Advance request cancelled.");
      await load();
    } catch (requestError) {
      setError(messageFrom(requestError));
    } finally {
      setBusy("");
    }
  }

  async function savePolicy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!policy) return;
    setBusy("policy");
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      await apiFetch<Policy>(`advance-policy/${policy.id}/`, {
        method: "PATCH",
        body: JSON.stringify({
          enabled: form.get("enabled") === "on",
          minimum_service_days: form.get("minimum_service_days"),
          max_earned_wage_percentage: form.get("max_earned_wage_percentage"),
          max_requests_per_cycle: form.get("max_requests_per_cycle"),
          minimum_amount: form.get("minimum_amount"),
          maximum_amount: form.get("maximum_amount") || null,
          acknowledgement_text: form.get("acknowledgement_text"),
          approver_roles: form.getAll("approver_roles"),
        }),
      });
      setModal(null);
      setNotice("Advance policy updated.");
      await load();
    } catch (requestError) {
      setError(messageFrom(requestError));
    } finally {
      setBusy("");
    }
  }

  if (!items || !me || !policy) return <LoadingState label="Loading advance workspace..." />;

  const pending = items.filter((item) => item.status === "requested").length;
  const outstanding = items
    .filter((item) => ["approved", "disbursed"].includes(item.status))
    .reduce((sum, item) => sum + Number(item.approved_amount), 0);
  const canDecide = policy.approver_roles.includes(me.role);
  const unlockedCycles = cycles.filter(
    (cycle) => !["locked", "exported", "paid"].includes(cycle.status),
  );

  return (
    <>
      <header className="page-head">
        <div>
          <p className="eyebrow">Controlled salary access</p>
          <h1>Advances</h1>
          <p>Request, approve, disburse, and reconcile every salary advance.</p>
        </div>
        <div className="inline-actions">
          {policyRoles.has(me.role) && (
            <button className="button secondary" onClick={() => setModal("policy")}>
              <Settings2 size={17} /> Policy
            </button>
          )}
          {requestRoles.has(me.role) && (
            <button className="button" onClick={() => setModal("create")}>
              <Plus size={17} /> New request
            </button>
          )}
        </div>
      </header>
      {error && <p className="sync-banner payroll-error">{error}</p>}
      {notice && <p className="sync-banner payroll-notice">{notice}</p>}
      <section className="grid stats">
        <article className="card stat"><div className="label">Awaiting decision</div><div className="value">{pending}</div><div className="hint">Requests in the approval queue</div></article>
        <article className="card stat"><div className="label">Outstanding</div><div className="value">AED {outstanding.toFixed(2)}</div><div className="hint">Approved and disbursed advances</div></article>
        <article className="card stat"><div className="label">Earned wage limit</div><div className="value">{policy.max_earned_wage_percentage}%</div><div className="hint">Maximum share available under policy</div></article>
        <article className="card stat"><div className="label">Requests per cycle</div><div className="value">{policy.max_requests_per_cycle}</div><div className="hint">{policy.enabled ? "Policy is active" : "Requests are disabled"}</div></article>
      </section>
      <div className="toolbar">
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search worker or code" />
        <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
          <option value="all">All statuses</option>
          {["requested", "approved", "rejected", "disbursed", "deducted", "cancelled"].map((status) => <option key={status}>{status}</option>)}
        </select>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Worker</th><th>Requested</th><th>Approved</th><th>Route</th><th>Requested at</th><th>Status</th><th>Action</th></tr></thead>
          <tbody>
            {filtered.map((item) => (
              <tr key={item.id}>
                <td><button className="table-link" onClick={() => setSelected(item)}>{item.worker_name}</button><br /><span className="muted">{item.worker_code}</span></td>
                <td>AED {item.requested_amount}</td>
                <td>AED {item.approved_amount}</td>
                <td>{item.requested_via.replaceAll("_", " ")}</td>
                <td>{new Date(item.created_at).toLocaleDateString()}</td>
                <td><Badge value={item.status} /></td>
                <td><button className="button secondary" onClick={() => setSelected(item)}>Review</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        {!filtered.length && <div className="empty">No advance requests match these filters.</div>}
      </div>

      {modal === "create" && (
        <div className="modal-backdrop"><form className="review-panel" onSubmit={createRequest}>
          <div className="review-head"><div><p className="eyebrow">New advance</p><h2>Request for a worker</h2><p>Eligibility is calculated from finalized daily earnings and existing advances.</p></div><button type="button" className="icon-button" onClick={() => setModal(null)}><X size={20} /></button></div>
          <div className="field" style={{ marginTop: "1rem" }}><label>Worker</label><select name="worker" required value={workerId} onChange={(event) => selectWorker(event.target.value)}><option value="">Select worker</option>{workers.map((worker) => <option value={worker.id} key={worker.id}>{worker.worker_code} · {worker.full_name}</option>)}</select></div>
          {eligibility && <div className="review-summary"><HandCoins size={18} /><span>Available now: <strong>AED {eligibility.available_limit}</strong> · Minimum request AED {eligibility.minimum_amount}</span></div>}
          <div className="field"><label>Requested amount</label><input name="amount" type="number" min={eligibility?.minimum_amount ?? "0.01"} max={eligibility?.available_limit} step="0.01" required /></div>
          <label className="payroll-profile-toggle"><input name="acknowledgement" type="checkbox" required /><span><strong>Confirm deduction</strong><small>{eligibility?.acknowledgement_text || policy.acknowledgement_text}</small></span></label>
          <div className="decision-actions" style={{ marginTop: "1rem" }}><button className="button" disabled={busy === "create" || !eligibility?.enabled}>Submit request</button><button type="button" className="button secondary" onClick={() => setModal(null)}>Cancel</button></div>
        </form></div>
      )}

      {modal === "policy" && (
        <div className="modal-backdrop"><form className="review-panel" onSubmit={savePolicy}>
          <div className="review-head"><div><p className="eyebrow">Company controls</p><h2>Advance policy</h2><p>Changes apply to future requests; existing decisions keep their snapshots.</p></div><button type="button" className="icon-button" onClick={() => setModal(null)}><X size={20} /></button></div>
          <label className="payroll-profile-toggle" style={{ margin: "1rem 0" }}><input name="enabled" type="checkbox" defaultChecked={policy.enabled} /><span><strong>Enable salary advances</strong><small>Workers and HR can submit new requests while enabled.</small></span></label>
          <div className="worker-form-grid">
            <div className="field"><label>Minimum service days</label><input name="minimum_service_days" type="number" min="0" defaultValue={policy.minimum_service_days} required /></div>
            <div className="field"><label>Earned wage limit %</label><input name="max_earned_wage_percentage" type="number" min="0" max="100" step="0.01" defaultValue={policy.max_earned_wage_percentage} required /></div>
            <div className="field"><label>Requests per cycle</label><input name="max_requests_per_cycle" type="number" min="1" defaultValue={policy.max_requests_per_cycle} required /></div>
            <div className="field"><label>Minimum AED</label><input name="minimum_amount" type="number" min="0" step="0.01" defaultValue={policy.minimum_amount} required /></div>
            <div className="field"><label>Maximum AED</label><input name="maximum_amount" type="number" min="0" step="0.01" defaultValue={policy.maximum_amount ?? ""} /></div>
            <div className="field span-2"><label>Worker acknowledgement</label><textarea name="acknowledgement_text" rows={3} defaultValue={policy.acknowledgement_text} required /></div>
          </div>
          <div className="field"><label>Roles allowed to approve</label><div className="inline-actions">{roleOptions.map((role) => <label className="role-check" key={role}><input type="checkbox" name="approver_roles" value={role} defaultChecked={policy.approver_roles.includes(role)} /> {role}</label>)}</div></div>
          <div className="decision-actions"><button className="button" disabled={busy === "policy"}>Save policy</button><button type="button" className="button secondary" onClick={() => setModal(null)}>Cancel</button></div>
        </form></div>
      )}

      {selected && (
        <div className="modal-backdrop"><section className="review-panel">
          <div className="review-head"><div><p className="eyebrow">Advance review</p><h2>{selected.worker_name}</h2><p>{selected.worker_code} · requested {new Date(selected.created_at).toLocaleString()}</p></div><button className="icon-button" onClick={() => setSelected(null)}><X size={20} /></button></div>
          <div className="advance-summary-grid">
            <div><span>Requested</span><strong>AED {selected.requested_amount}</strong></div>
            <div><span>Limit at request</span><strong>AED {selected.available_limit_snapshot}</strong></div>
            <div><span>Current limit</span><strong>AED {selected.available_limit}</strong></div>
            <div><span>Status</span><Badge value={selected.status} /></div>
          </div>
          <div className="case-note"><strong>Deduction acknowledgement</strong><p>{selected.acknowledgement_text}</p></div>
          {selected.decision_reason && <div className="case-note"><strong>Decision note</strong><p>{selected.decision_reason}</p></div>}
          {selected.deduction_cycle_name && <div className="review-summary"><Landmark size={18} /><span>Deduct through <strong>{selected.deduction_cycle_name}</strong>. It becomes deducted when that cycle is locked.</span></div>}
          {selected.status === "requested" && canDecide && (
            <form onSubmit={(event) => decide(true, event)}>
              <div className="field"><label>Approved amount</label><input name="amount" type="number" min="0.01" max={Math.min(Number(selected.requested_amount), Number(selected.available_limit))} step="0.01" defaultValue={selected.requested_amount} required /></div>
              <div className="field"><label>Decision note</label><textarea name="reason" rows={3} placeholder="Reason for approval, reduced amount, or rejection" /></div>
              <div className="decision-actions"><button className="button" disabled={busy === "decision"}><CheckCircle2 size={16} /> Approve</button><button type="button" className="button danger" disabled={busy === "decision"} onClick={() => { const form = document.activeElement?.closest("form") as HTMLFormElement | null; if (form) void decide(false, { preventDefault() {}, currentTarget: form } as unknown as FormEvent<HTMLFormElement>); }}><XCircle size={16} /> Reject</button></div>
            </form>
          )}
          {selected.status === "requested" && requestRoles.has(me.role) && !canDecide && <button className="button danger" disabled={busy === "cancel"} onClick={cancelRequest}>Cancel request</button>}
          {selected.status === "approved" && disbursementRoles.has(me.role) && (
            <form onSubmit={disburse}>
              <div className="field"><label>Payment reference</label><input name="reference" minLength={3} placeholder="Bank transfer or cash voucher reference" required /></div>
              <div className="field"><label>Deduction payroll cycle</label><select name="deduction_cycle" required><option value="">Select cycle</option>{unlockedCycles.map((cycle) => <option key={cycle.id} value={cycle.id}>{cycle.name} · {cycle.status}</option>)}</select></div>
              <button className="button" disabled={busy === "disburse"}><Landmark size={16} /> Mark disbursed</button>
            </form>
          )}
        </section></div>
      )}
    </>
  );
}
