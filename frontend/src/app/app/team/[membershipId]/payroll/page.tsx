"use client";

import { ArrowLeft, Save } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { ErrorState, LoadingState } from "@/components/page-state";
import { ApiError, apiFetch } from "@/lib/api";

type Membership = {
  id: string;
  role: string;
  payroll_profile_id: string | null;
  user: { name: string; phone: string; email: string };
};

function fieldErrors(error: unknown) {
  if (!(error instanceof ApiError) || !error.details || typeof error.details !== "object") {
    return {};
  }
  return Object.fromEntries(
    Object.entries(error.details as Record<string, unknown>).map(([key, value]) => [
      key,
      Array.isArray(value) ? value.join(" ") : String(value),
    ]),
  );
}

export default function LinkStaffPayrollPage() {
  const { membershipId } = useParams<{ membershipId: string }>();
  const router = useRouter();
  const [member, setMember] = useState<Membership | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    apiFetch<Membership>(`memberships/${membershipId}/`)
      .then(setMember)
      .catch((caught) =>
        setError(caught instanceof Error ? caught.message : "Unable to load staff member."),
      );
  }, [membershipId]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setErrors({});
    try {
      await apiFetch(`memberships/${membershipId}/payroll-profile/`, {
        method: "POST",
        body: JSON.stringify({
          worker_code: form.get("worker_code"),
          department: form.get("department"),
          job_title: form.get("job_title"),
          employment_start_date: form.get("employment_start_date"),
          basic_wage: form.get("basic_wage"),
          allowances: [
            {
              name: String(form.get("allowance_name") ?? "").trim(),
              amount: form.get("allowance_amount"),
              frequency: "monthly",
            },
          ].filter((allowance) => allowance.name && Number(allowance.amount) > 0),
          payroll_method: form.get("payroll_method"),
          bank_routing_code: form.get("bank_routing_code"),
          bank_account_or_card: form.get("bank_account_or_card"),
        }),
      });
      router.push("/app/team");
      router.refresh();
    } catch (caught) {
      setErrors(fieldErrors(caught));
      setError(caught instanceof Error ? caught.message : "Unable to link payroll profile.");
    } finally {
      setBusy(false);
    }
  }

  if (error && !member) return <ErrorState message={error} />;
  if (!member) return <LoadingState label="Loading staff member..." />;
  if (member.payroll_profile_id) {
    return <ErrorState message="This staff account already has a payroll profile." />;
  }

  return (
    <>
      <Link className="button secondary detail-back" href="/app/team">
        <ArrowLeft size={16} /> Back to team
      </Link>
      <header className="page-head">
        <div>
          <p className="eyebrow">Link payroll identity</p>
          <h1>{member.user.name}</h1>
          <p>{member.user.phone} · {member.role.replaceAll("_", " ")}</p>
        </div>
      </header>
      {error && <p className="sync-banner payroll-error">{error}</p>}
      <form onSubmit={submit}>
        <section className="card worker-form-section">
          <div className="section-heading">
            <div>
              <h2>Employment & salary</h2>
              <p>This adds payroll to the existing login without changing its permissions.</p>
            </div>
          </div>
          <div className="worker-form-grid">
            <div className="field">
              <label htmlFor="link-code">Employee code</label>
              <input id="link-code" name="worker_code" required />
              {errors.worker_code && <span className="error">{errors.worker_code}</span>}
            </div>
            <div className="field">
              <label htmlFor="link-department">Department</label>
              <input id="link-department" name="department" />
            </div>
            <div className="field">
              <label htmlFor="link-title">Job title</label>
              <input id="link-title" name="job_title" />
            </div>
            <div className="field">
              <label htmlFor="link-start">Employment start</label>
              <input
                defaultValue={new Date().toISOString().slice(0, 10)}
                id="link-start"
                name="employment_start_date"
                required
                type="date"
              />
            </div>
            <div className="field">
              <label htmlFor="link-wage">Monthly basic wage (AED)</label>
              <input
                id="link-wage"
                min="0.01"
                name="basic_wage"
                required
                step="0.01"
                type="number"
              />
              {errors.basic_wage && <span className="error">{errors.basic_wage}</span>}
            </div>
            <div className="field">
              <label htmlFor="link-allowance-name">Monthly allowance</label>
              <input id="link-allowance-name" name="allowance_name" placeholder="Transport" />
            </div>
            <div className="field">
              <label htmlFor="link-allowance-amount">Allowance amount (AED)</label>
              <input
                id="link-allowance-amount"
                min="0"
                name="allowance_amount"
                step="0.01"
                type="number"
              />
            </div>
            <div className="field">
              <label htmlFor="link-method">Payroll method</label>
              <select defaultValue="bank" id="link-method" name="payroll_method">
                <option value="bank">Bank transfer</option>
                <option value="card">Payroll card</option>
                <option value="cash">Cash</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="link-routing">Bank routing code</label>
              <input id="link-routing" name="bank_routing_code" />
            </div>
            <div className="field span-2">
              <label htmlFor="link-account">Account / payroll card</label>
              <input id="link-account" name="bank_account_or_card" />
            </div>
          </div>
        </section>
        <div className="worker-form-actions">
          <Link className="button secondary" href="/app/team">Cancel</Link>
          <button className="button" disabled={busy}>
            <Save size={17} /> {busy ? "Linking payroll..." : "Create payroll profile"}
          </button>
        </div>
      </form>
    </>
  );
}
