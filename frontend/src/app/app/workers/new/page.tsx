"use client";

import { ArrowLeft, Plus, Save, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { ErrorState, LoadingState } from "@/components/page-state";
import { ApiError, apiFetch } from "@/lib/api";

type Option = { value: string; label: string };
type CreationOptions = {
  sites: { id: string; name: string; address: string }[];
  supervisors: { id: string; name: string; phone: string; site_ids: string[] }[];
  wage_types: Option[];
  notification_channels: Option[];
};

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

export default function CreateWorkerPage() {
  const router = useRouter();
  const [options, setOptions] = useState<CreationOptions | null>(null);
  const [selectedSite, setSelectedSite] = useState("");
  const [allowances, setAllowances] = useState<Allowance[]>([
    { id: 1, name: "Food", amount: "", frequency: "monthly" },
  ]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    apiFetch<CreationOptions>("workers/creation-options/")
      .then(setOptions)
      .catch((caught) =>
        setError(caught instanceof Error ? caught.message : "Unable to load worker setup."),
      );
  }, []);

  const supervisors = useMemo(
    () =>
      options?.supervisors.filter(
        (supervisor) =>
          !selectedSite || supervisor.site_ids.includes(selectedSite),
      ) ?? [],
    [options, selectedSite],
  );

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
      worker_code: form.get("worker_code"),
      full_name: form.get("full_name"),
      phone: form.get("phone"),
      nationality: form.get("nationality"),
      preferred_language: form.get("preferred_language"),
      notification_channel: form.get("notification_channel"),
      job_title: form.get("job_title"),
      employment_start_date: form.get("employment_start_date"),
      status: form.get("status"),
      wage_type: form.get("wage_type"),
      basic_wage: form.get("basic_wage"),
      allowances: allowances
        .filter((allowance) => allowance.name.trim() && Number(allowance.amount) > 0)
        .map(({ name, amount, frequency }) => ({ name, amount, frequency })),
      payroll_method: form.get("payroll_method"),
      bank_routing_code: form.get("bank_routing_code"),
      bank_account_or_card: form.get("bank_account_or_card"),
      default_site: form.get("default_site") || null,
      supervisor: form.get("supervisor") || null,
    };
    try {
      await apiFetch("workers/", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      router.push("/app/workers");
      router.refresh();
    } catch (caught) {
      setErrors(fieldErrors(caught));
      setError(caught instanceof Error ? caught.message : "Unable to create worker.");
    } finally {
      setBusy(false);
    }
  }

  if (error && !options) return <ErrorState message={error} />;
  if (!options) return <LoadingState label="Loading worker setup..." />;

  return (
    <>
      <Link className="button secondary detail-back" href="/app/workers">
        <ArrowLeft size={16} /> Back to workers
      </Link>
      <header className="page-head">
        <div>
          <p className="eyebrow">Worker onboarding</p>
          <h1>Create worker</h1>
          <p>Add employment, site, wage, allowance, and payroll information.</p>
        </div>
      </header>

      {error && <p className="sync-banner payroll-error">{error}</p>}

      <form onSubmit={submit}>
        <section className="card worker-form-section">
          <div className="section-heading">
            <div>
              <h2>Personal details</h2>
              <p>Identity and communication information used across operations.</p>
            </div>
          </div>
          <div className="worker-form-grid">
            <div className="field">
              <label htmlFor="worker-code">Worker code</label>
              <input id="worker-code" name="worker_code" placeholder="PY-0013" required />
              {errors.worker_code && <span className="error">{errors.worker_code}</span>}
            </div>
            <div className="field span-2">
              <label htmlFor="full-name">Full name</label>
              <input id="full-name" name="full_name" required />
              {errors.full_name && <span className="error">{errors.full_name}</span>}
            </div>
            <div className="field">
              <label htmlFor="phone">Phone</label>
              <input id="phone" name="phone" placeholder="+971 50 123 4567" type="tel" />
              {errors.phone && <span className="error">{errors.phone}</span>}
            </div>
            <div className="field">
              <label htmlFor="nationality">Nationality</label>
              <input id="nationality" name="nationality" />
            </div>
            <div className="field">
              <label htmlFor="job-title">Job title</label>
              <input id="job-title" name="job_title" placeholder="Cleaner" />
            </div>
            <div className="field">
              <label htmlFor="language">Preferred language</label>
              <select defaultValue="en" id="language" name="preferred_language">
                <option value="en">English</option>
                <option value="ar">Arabic</option>
                <option value="hi">Hindi</option>
                <option value="ur">Urdu</option>
                <option value="bn">Bengali</option>
                <option value="ne">Nepali</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="notification-channel">Worker updates</label>
              <select
                defaultValue="whatsapp"
                id="notification-channel"
                name="notification_channel"
              >
                {options.notification_channels.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </div>
          </div>
        </section>

        <section className="card worker-form-section">
          <div className="section-heading">
            <div>
              <h2>Employment & site</h2>
              <p>Active workers require both a site and its assigned supervisor.</p>
            </div>
          </div>
          <div className="worker-form-grid">
            <div className="field">
              <label htmlFor="employment-start">Employment start</label>
              <input
                defaultValue={new Date().toISOString().slice(0, 10)}
                id="employment-start"
                name="employment_start_date"
                required
                type="date"
              />
            </div>
            <div className="field">
              <label htmlFor="worker-status">Initial status</label>
              <select defaultValue="active" id="worker-status" name="status">
                <option value="active">Active</option>
                <option value="draft">Draft</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="default-site">Default site</label>
              <select
                id="default-site"
                name="default_site"
                value={selectedSite}
                onChange={(event) => setSelectedSite(event.target.value)}
              >
                <option value="">Select site</option>
                {options.sites.map((site) => (
                  <option key={site.id} value={site.id}>{site.name}</option>
                ))}
              </select>
              {errors.default_site && <span className="error">{errors.default_site}</span>}
            </div>
            <div className="field">
              <label htmlFor="supervisor">Supervisor</label>
              <select id="supervisor" key={selectedSite} name="supervisor">
                <option value="">Select supervisor</option>
                {supervisors.map((supervisor) => (
                  <option key={supervisor.id} value={supervisor.id}>
                    {supervisor.name} · {supervisor.phone}
                  </option>
                ))}
              </select>
              {selectedSite && !supervisors.length && (
                <span className="error">No active supervisor is assigned to this site.</span>
              )}
              {errors.supervisor && <span className="error">{errors.supervisor}</span>}
            </div>
          </div>
        </section>

        <section className="card worker-form-section">
          <div className="section-heading">
            <div>
              <h2>Wage & allowances</h2>
              <p>Configure the contractual base and recurring or daily additions.</p>
            </div>
          </div>
          <div className="worker-form-grid wage-grid">
            <div className="field">
              <label htmlFor="wage-type">Wage type</label>
              <select defaultValue="monthly" id="wage-type" name="wage_type">
                {options.wage_types.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="basic-wage">Basic wage (AED)</label>
              <input
                id="basic-wage"
                min="0"
                name="basic_wage"
                required
                step="0.01"
                type="number"
              />
              {errors.basic_wage && <span className="error">{errors.basic_wage}</span>}
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
                  <select
                    value={allowance.frequency}
                    onChange={(event) =>
                      updateAllowance(allowance.id, {
                        frequency: event.target.value as "monthly" | "daily",
                      })
                    }
                  >
                    <option value="monthly">Monthly</option>
                    <option value="daily">Per working day</option>
                  </select>
                </div>
                <button
                  aria-label={`Remove ${allowance.name || "allowance"}`}
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

        <section className="card worker-form-section">
          <div className="section-heading">
            <div>
              <h2>Payroll details</h2>
              <p>Sensitive account identifiers are encrypted and never returned by the API.</p>
            </div>
          </div>
          <div className="worker-form-grid">
            <div className="field">
              <label htmlFor="payroll-method">Payroll method</label>
              <select defaultValue="card" id="payroll-method" name="payroll_method">
                <option value="card">Payroll card</option>
                <option value="bank">Bank transfer</option>
                <option value="cash">Cash</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="routing-code">Bank routing code</label>
              <input id="routing-code" name="bank_routing_code" />
            </div>
            <div className="field span-2">
              <label htmlFor="account-card">Account / payroll card number</label>
              <input id="account-card" name="bank_account_or_card" />
              {errors.bank_account_or_card && (
                <span className="error">{errors.bank_account_or_card}</span>
              )}
            </div>
          </div>
        </section>

        <div className="worker-form-actions">
          <Link className="button secondary" href="/app/workers">Cancel</Link>
          <button className="button" disabled={busy}>
            <Save size={17} /> {busy ? "Creating worker..." : "Create worker"}
          </button>
        </div>
      </form>
    </>
  );
}
