"use client";

import { ArrowLeft, Eye, EyeOff, Plus, Save, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { ErrorState, LoadingState } from "@/components/page-state";
import { ApiError, apiFetch } from "@/lib/api";
import type { Me } from "@/lib/types";

type Allowance = {
  id: number;
  name: string;
  amount: string;
  frequency: "monthly" | "daily";
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

function temporaryPassword() {
  return `PayYard!${crypto.randomUUID().replaceAll("-", "").slice(0, 10)}Aa1`;
}

export default function StaffOnboardingPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [withPayroll, setWithPayroll] = useState(true);
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [allowances, setAllowances] = useState<Allowance[]>([
    { id: 1, name: "Transport", amount: "", frequency: "monthly" },
  ]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    apiFetch<Me>("auth/me/")
      .then((profile) => {
        setMe(profile);
        setPassword(temporaryPassword());
      })
      .catch((caught) =>
        setError(caught instanceof Error ? caught.message : "Unable to load onboarding."),
      );
  }, []);

  function updateAllowance(id: number, patch: Partial<Allowance>) {
    setAllowances((current) =>
      current.map((allowance) =>
        allowance.id === id ? { ...allowance, ...patch } : allowance,
      ),
    );
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setErrors({});
    const payload = {
      name: form.get("name"),
      phone: form.get("phone"),
      email: form.get("email"),
      preferred_language: form.get("preferred_language"),
      role: form.get("role"),
      temporary_password: password,
      create_payroll_profile: withPayroll,
      worker_code: withPayroll ? form.get("worker_code") : "",
      department: withPayroll ? form.get("department") : "",
      job_title: withPayroll ? form.get("job_title") : "",
      employment_start_date: withPayroll ? form.get("employment_start_date") : null,
      basic_wage: withPayroll ? form.get("basic_wage") : null,
      allowances: withPayroll
        ? allowances
            .filter((allowance) => allowance.name.trim() && Number(allowance.amount) > 0)
            .map(({ name, amount, frequency }) => ({ name, amount, frequency }))
        : [],
      payroll_method: withPayroll ? form.get("payroll_method") : "",
      bank_routing_code: withPayroll ? form.get("bank_routing_code") : "",
      bank_account_or_card: withPayroll ? form.get("bank_account_or_card") : "",
    };
    try {
      await apiFetch("memberships/onboard/", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      router.push("/app/team");
      router.refresh();
    } catch (caught) {
      setErrors(fieldErrors(caught));
      setError(caught instanceof Error ? caught.message : "Unable to onboard staff member.");
    } finally {
      setBusy(false);
    }
  }

  if (error && !me) return <ErrorState message={error} />;
  if (!me) return <LoadingState label="Loading staff onboarding..." />;

  const roles = me.role === "owner"
    ? ["admin", "hr", "finance", "payroll", "operations", "supervisor", "owner"]
    : ["hr", "finance", "payroll", "operations", "supervisor"];

  return (
    <>
      <Link className="button secondary detail-back" href="/app/team">
        <ArrowLeft size={16} /> Back to team
      </Link>
      <header className="page-head">
        <div>
          <p className="eyebrow">Secure onboarding</p>
          <h1>Onboard staff member</h1>
          <p>Create company access and, when applicable, a linked payroll identity.</p>
        </div>
      </header>

      {error && <p className="sync-banner payroll-error">{error}</p>}

      <form onSubmit={submit}>
        <section className="card worker-form-section">
          <div className="section-heading">
            <div>
              <h2>Login & role</h2>
              <p>The phone number and temporary password are used for first login.</p>
            </div>
          </div>
          <div className="worker-form-grid">
            <div className="field span-2">
              <label htmlFor="staff-name">Full name</label>
              <input id="staff-name" name="name" required />
              {errors.name && <span className="error">{errors.name}</span>}
            </div>
            <div className="field">
              <label htmlFor="staff-phone">Phone</label>
              <input
                id="staff-phone"
                name="phone"
                placeholder="+971 50 123 4567"
                required
                type="tel"
              />
              {errors.phone && <span className="error">{errors.phone}</span>}
            </div>
            <div className="field">
              <label htmlFor="staff-email">Email</label>
              <input id="staff-email" name="email" type="email" />
            </div>
            <div className="field">
              <label htmlFor="staff-role">Company role</label>
              <select defaultValue="hr" id="staff-role" name="role">
                {roles.map((role) => (
                  <option key={role} value={role}>
                    {role.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())}
                  </option>
                ))}
              </select>
              {errors.role && <span className="error">{errors.role}</span>}
            </div>
            <div className="field">
              <label htmlFor="staff-language">Preferred language</label>
              <select defaultValue="en" id="staff-language" name="preferred_language">
                <option value="en">English</option>
                <option value="ar">Arabic</option>
                <option value="hi">Hindi</option>
                <option value="ur">Urdu</option>
              </select>
            </div>
            <div className="field span-2">
              <label htmlFor="temporary-password">Temporary password</label>
              <div className="password-field">
                <input
                  id="temporary-password"
                  minLength={12}
                  required
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
                <button
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  className="icon-button"
                  onClick={() => setShowPassword((value) => !value)}
                  type="button"
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {errors.temporary_password && (
                <span className="error">{errors.temporary_password}</span>
              )}
            </div>
          </div>
        </section>

        <section className="card worker-form-section">
          <label className="payroll-profile-toggle">
            <input
              checked={withPayroll}
              onChange={(event) => setWithPayroll(event.target.checked)}
              type="checkbox"
            />
            <span>
              <strong>Create a payroll profile</strong>
              <small>
                Enable this when the staff member is paid through PayYard. Access-only
                consultants can be onboarded without one.
              </small>
            </span>
          </label>
        </section>

        {withPayroll && (
          <>
            <section className="card worker-form-section">
              <div className="section-heading">
                <div>
                  <h2>Employment & salary</h2>
                  <p>Staff compensation is fixed monthly and does not require a site roster.</p>
                </div>
              </div>
              <div className="worker-form-grid">
                <div className="field">
                  <label htmlFor="staff-code">Employee code</label>
                  <input id="staff-code" name="worker_code" placeholder="ST-001" required />
                  {errors.worker_code && <span className="error">{errors.worker_code}</span>}
                </div>
                <div className="field">
                  <label htmlFor="department">Department</label>
                  <input id="department" name="department" placeholder="Human Resources" />
                </div>
                <div className="field">
                  <label htmlFor="staff-job-title">Job title</label>
                  <input id="staff-job-title" name="job_title" placeholder="HR Officer" />
                </div>
                <div className="field">
                  <label htmlFor="staff-start">Employment start</label>
                  <input
                    defaultValue={new Date().toISOString().slice(0, 10)}
                    id="staff-start"
                    name="employment_start_date"
                    required
                    type="date"
                  />
                </div>
                <div className="field">
                  <label htmlFor="staff-wage">Monthly basic wage (AED)</label>
                  <input
                    id="staff-wage"
                    min="0.01"
                    name="basic_wage"
                    required
                    step="0.01"
                    type="number"
                  />
                  {errors.basic_wage && <span className="error">{errors.basic_wage}</span>}
                </div>
                <div className="field">
                  <label htmlFor="staff-payroll-method">Payroll method</label>
                  <select defaultValue="bank" id="staff-payroll-method" name="payroll_method">
                    <option value="bank">Bank transfer</option>
                    <option value="card">Payroll card</option>
                    <option value="cash">Cash</option>
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="staff-routing">Bank routing code</label>
                  <input id="staff-routing" name="bank_routing_code" />
                </div>
                <div className="field">
                  <label htmlFor="staff-account">Account / payroll card</label>
                  <input id="staff-account" name="bank_account_or_card" />
                </div>
              </div>
            </section>

            <section className="card worker-form-section">
              <div className="section-heading">
                <div>
                  <h2>Monthly allowances</h2>
                  <p>Add recurring staff benefits such as transport or housing.</p>
                </div>
              </div>
              <div className="allowance-list">
                {allowances.map((allowance) => (
                  <div className="allowance-row" key={allowance.id}>
                    <div className="field">
                      <label>Allowance name</label>
                      <input
                        value={allowance.name}
                        onChange={(event) =>
                          updateAllowance(allowance.id, { name: event.target.value })
                        }
                      />
                    </div>
                    <div className="field">
                      <label>Amount (AED)</label>
                      <input
                        min="0"
                        step="0.01"
                        type="number"
                        value={allowance.amount}
                        onChange={(event) =>
                          updateAllowance(allowance.id, { amount: event.target.value })
                        }
                      />
                    </div>
                    <div className="field">
                      <label>Frequency</label>
                      <select disabled value="monthly">
                        <option value="monthly">Monthly</option>
                      </select>
                    </div>
                    <button
                      aria-label="Remove allowance"
                      className="icon-button allowance-remove"
                      disabled={allowances.length === 1}
                      onClick={() =>
                        setAllowances((current) =>
                          current.filter((item) => item.id !== allowance.id),
                        )
                      }
                      type="button"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
                <button
                  className="button secondary add-allowance"
                  onClick={() =>
                    setAllowances((current) => [
                      ...current,
                      {
                        id: Math.max(...current.map((item) => item.id), 0) + 1,
                        name: "",
                        amount: "",
                        frequency: "monthly",
                      },
                    ])
                  }
                  type="button"
                >
                  <Plus size={16} /> Add allowance
                </button>
              </div>
            </section>
          </>
        )}

        <div className="worker-form-actions">
          <Link className="button secondary" href="/app/team">Cancel</Link>
          <button className="button" disabled={busy}>
            <Save size={17} /> {busy ? "Onboarding..." : "Onboard staff member"}
          </button>
        </div>
      </form>
    </>
  );
}
