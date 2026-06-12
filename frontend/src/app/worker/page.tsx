"use client";

import { Banknote, CalendarCheck, HandCoins, LogOut, MessageSquareWarning } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/page-state";

type WorkerProfile = { id: string; full_name: string; worker_code: string; company?: string; available_advance_limit: string };
type Attendance = { id: string; work_date: string; site_name: string; check_in_at: string; check_out_at: string | null; status: string; flags: string[] };
type Wage = { id: string; work_date: string; regular_minutes: number; overtime_minutes: number; net_estimate: string; status: string };
type Advance = { id: string; requested_amount: string; approved_amount: string; status: string; created_at: string };
type Dispute = { id: string; dispute_type: string; date_reference: string; status: string; description: string };

async function workerFetch<T>(path: string, token: string, init: RequestInit = {}) {
  const response = await fetch(`/api/worker/${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", "X-Worker-Token": token, ...init.headers },
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data?.error?.detail ?? data?.detail ?? "Request failed.");
  return data as T;
}

export default function WorkerPortalPage() {
  const [challenge, setChallenge] = useState("");
  const [debugCode, setDebugCode] = useState("");
  const [profile, setProfile] = useState<WorkerProfile | null>(null);
  const [attendance, setAttendance] = useState<Attendance[]>([]);
  const [wages, setWages] = useState<Wage[]>([]);
  const [advances, setAdvances] = useState<Advance[]>([]);
  const [disputes, setDisputes] = useState<Dispute[]>([]);
  const [tab, setTab] = useState("attendance");
  const [error, setError] = useState("");

  const load = useCallback(async (activeToken: string) => {
    const [me, attendanceRows, wageRows, advanceRows, disputeRows] = await Promise.all([
      workerFetch<WorkerProfile>("me/", activeToken),
      workerFetch<Attendance[]>("attendance/", activeToken),
      workerFetch<Wage[]>("wages/", activeToken),
      workerFetch<Advance[]>("advances/", activeToken),
      workerFetch<Dispute[]>("disputes/", activeToken),
    ]);
    setProfile(me); setAttendance(attendanceRows); setWages(wageRows); setAdvances(advanceRows); setDisputes(disputeRows);
  }, []);

  useEffect(() => {
    const stored = sessionStorage.getItem("payyard-worker-token");
    if (stored) {
      queueMicrotask(() => {
        void load(stored).catch(() =>
          sessionStorage.removeItem("payyard-worker-token"),
        );
      });
    }
  }, [load]);

  async function requestOtp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/backend/worker-auth/request-otp/", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_slug: form.get("company_slug"), phone: form.get("phone") }),
    });
    const data = await response.json();
    if (!response.ok) return setError(data?.error?.detail ?? "Unable to send code.");
    setChallenge(data.challenge_id ?? ""); setDebugCode(data.debug_code ?? "");
  }

  async function verifyOtp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/backend/worker-auth/verify-otp/", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ challenge_id: challenge, code: form.get("code") }),
    });
    const data = await response.json();
    if (!response.ok) return setError(data?.error?.detail ?? "Invalid code.");
    sessionStorage.setItem("payyard-worker-token", data.token);
    await load(data.token);
  }

  if (!profile) return (
    <main className="auth-shell">
      <section className="auth-story"><div className="brand"><span className="brand-mark">P</span> PayYard</div><div><p className="eyebrow">Private worker access</p><h1>Your work. Your wages. Clearly.</h1><p>Review attendance, daily earnings, advances, payslips, and issue status through a short-lived phone verification session.</p></div><p>Detailed payroll data stays behind verification and is not sent in chat messages.</p></section>
      <section className="auth-panel">
        {!challenge ? <form className="auth-card" onSubmit={requestOtp}><p className="eyebrow">Worker portal</p><h2>Verify your phone</h2><p>We will send a six-digit code to your registered number.</p><div className="field"><label>Company workspace</label><input name="company_slug" defaultValue="payyard-demo" required /></div><div className="field"><label>Phone number</label><input name="phone" type="tel" placeholder="+971 50 000 1001" required /></div>{error && <p className="error">{error}</p>}<button className="button full">Send code</button></form>
        : <form className="auth-card" onSubmit={verifyOtp}><p className="eyebrow">One-time code</p><h2>Enter verification code</h2><p>The code expires after five minutes.</p>{debugCode && <p className="sync-banner">Development code: <strong>{debugCode}</strong></p>}<div className="field"><label>Six-digit code</label><input name="code" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} required /></div>{error && <p className="error">{error}</p>}<button className="button full">Open my portal</button></form>}
      </section>
    </main>
  );

  const tabs = [["attendance", "Attendance", CalendarCheck], ["wages", "Wages", Banknote], ["advances", "Advances", HandCoins], ["disputes", "Issues", MessageSquareWarning]] as const;
  return (
    <main style={{ maxWidth: 920, margin: "0 auto", padding: "1rem" }}>
      <header className="card" style={{ background: "var(--green-2)", color: "white", marginBottom: "1rem" }}>
        <div className="brand"><span className="brand-mark">P</span> PayYard</div>
        <div style={{ marginTop: "2rem", display: "flex", justifyContent: "space-between", alignItems: "end" }}><div><p style={{ color: "#b9cdc4", marginBottom: ".25rem" }}>{profile.worker_code}</p><h1 style={{ marginBottom: 0 }}>{profile.full_name}</h1></div><button className="button secondary" onClick={() => { sessionStorage.removeItem("payyard-worker-token"); location.reload(); }}><LogOut size={16} /> Exit</button></div>
      </header>
      <nav className="toolbar">{tabs.map(([key, label, Icon]) => <button key={key} className={`button ${tab === key ? "" : "secondary"}`} onClick={() => setTab(key)}><Icon size={16} /> {label}</button>)}</nav>
      {tab === "attendance" && <div className="table-wrap"><table><thead><tr><th>Date</th><th>Site</th><th>Check in</th><th>Check out</th><th>Status</th></tr></thead><tbody>{attendance.map((item) => <tr key={item.id}><td>{item.work_date}</td><td>{item.site_name}</td><td>{new Date(item.check_in_at).toLocaleTimeString()}</td><td>{item.check_out_at ? new Date(item.check_out_at).toLocaleTimeString() : "Pending"}</td><td><Badge value={item.status} /></td></tr>)}</tbody></table></div>}
      {tab === "wages" && <div className="table-wrap"><table><thead><tr><th>Date</th><th>Regular</th><th>Overtime</th><th>Estimated net</th><th>Status</th></tr></thead><tbody>{wages.map((item) => <tr key={item.id}><td>{item.work_date}</td><td>{Math.round(item.regular_minutes / 60 * 10) / 10} h</td><td>{Math.round(item.overtime_minutes / 60 * 10) / 10} h</td><td>AED {item.net_estimate}</td><td><Badge value={item.status} /></td></tr>)}</tbody></table></div>}
      {tab === "advances" && <><div className="card stat" style={{ marginBottom: "1rem" }}><div className="label">Available advance estimate</div><div className="value">AED {profile.available_advance_limit}</div><div className="hint">Final approval follows employer policy.</div></div><div className="table-wrap"><table><thead><tr><th>Requested</th><th>Approved</th><th>Date</th><th>Status</th></tr></thead><tbody>{advances.map((item) => <tr key={item.id}><td>AED {item.requested_amount}</td><td>AED {item.approved_amount}</td><td>{new Date(item.created_at).toLocaleDateString()}</td><td><Badge value={item.status} /></td></tr>)}</tbody></table></div></>}
      {tab === "disputes" && <div className="table-wrap"><table><thead><tr><th>Date</th><th>Issue</th><th>Description</th><th>Status</th></tr></thead><tbody>{disputes.map((item) => <tr key={item.id}><td>{item.date_reference}</td><td>{item.dispute_type.replaceAll("_", " ")}</td><td>{item.description}</td><td><Badge value={item.status} /></td></tr>)}</tbody></table></div>}
    </main>
  );
}
