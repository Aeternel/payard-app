"use client";

import {
  CheckCircle2,
  Eye,
  FileDown,
  FileSpreadsheet,
  FileText,
  LockKeyhole,
  Pencil,
  PlayCircle,
  Plus,
  RotateCcw,
  Save,
  Settings2,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { Badge, ErrorState, LoadingState } from "@/components/page-state";
import { apiFetch, apiUrl, fetchAll } from "@/lib/api";
import { canApprovePayroll, canManagePayroll } from "@/lib/access";
import type { Me } from "@/lib/types";

type Cycle = {
  id: string;
  name: string;
  period_start: string;
  period_end: string;
  status: string;
  line_count: number;
  total_net_pay: string | null;
  readiness_snapshot: { score?: number };
};

type PayrollSetting = {
  id: string;
  half_day_deduction_percentage: string;
};

type PayrollLine = {
  id: string;
  worker_name: string;
  worker_code: string;
  contract_basic: string;
  gross_pay: string;
  calculated_net_pay: string;
  net_pay: string;
  manual_net_pay: string | null;
  manual_override_reason: string;
  flags: string[];
};

const operatorRoles = new Set(["hr", "payroll", "finance", "admin", "owner"]);
const reportFormats = ["html", "pdf", "excel"] as const;
type ReportFormat = (typeof reportFormats)[number];

type PayrollExport = {
  id: string;
  cycle: string;
  export_type: string;
  version: number;
  status: string;
  row_count: number;
  error: string;
  completed_at: string | null;
  created_at: string;
  download_url: string | null;
};

function money(value: string | null) {
  return Number(value ?? 0).toLocaleString("en-AE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function reportLabel(format: ReportFormat) {
  return format === "html" ? "HTML" : format === "pdf" ? "PDF" : "Excel";
}

function filenameFromDisposition(disposition: string | null, fallback: string) {
  const match = disposition?.match(/filename="([^"]+)"/i);
  return match?.[1] ?? fallback;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function LineEditor({
  line,
  canManage,
  editable,
  onSaved,
}: {
  line: PayrollLine;
  canManage: boolean;
  editable: boolean;
  onSaved: () => Promise<void>;
}) {
  const [amount, setAmount] = useState(line.manual_net_pay ?? line.net_pay);
  const [reason, setReason] = useState(line.manual_override_reason);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(netPay: string | null) {
    if (reason.trim().length < 5) {
      setError("Add a reason of at least five characters.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await apiFetch(`payroll-lines/${line.id}/override/`, {
        method: "POST",
        body: JSON.stringify({ net_pay: netPay, reason }),
      });
      await onSaved();
      setEditing(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to update pay.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <tr>
      <td>
        <Link className="worker-pay-link" href={`/app/payroll/${line.id}`}>
          {line.worker_name}
        </Link>
        <br />
        <span className="muted">{line.worker_code}</span>
      </td>
      <td>AED {money(line.contract_basic)}</td>
      <td>AED {money(line.gross_pay)}</td>
      <td>AED {money(line.calculated_net_pay)}</td>
      <td>
        <strong>AED {money(line.net_pay)}</strong>
        {line.manual_net_pay !== null && (
          <>
            <br />
            <span className="badge warn">Manual override</span>
          </>
        )}
      </td>
      <td className="payroll-line-action">
        {canManage && editable ? (
          editing ? (
            <div className="payroll-override">
              <div className="money-input">
                <span>AED</span>
                <input
                  aria-label={`Final pay for ${line.worker_name}`}
                  min="0"
                  step="0.01"
                  type="number"
                  value={amount}
                  onChange={(event) => setAmount(event.target.value)}
                />
              </div>
              <input
                aria-label={`Override reason for ${line.worker_name}`}
                placeholder="Required reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
              <div className="inline-actions">
                <button
                  className="button"
                  disabled={busy}
                  onClick={() => submit(amount)}
                >
                  <Save size={15} /> Save
                </button>
                {line.manual_net_pay !== null && (
                  <button
                    className="button secondary"
                    disabled={busy}
                    onClick={() => submit(null)}
                  >
                    <RotateCcw size={15} /> Use calculated
                  </button>
                )}
              </div>
              {error && <span className="error">{error}</span>}
            </div>
          ) : (
            <button className="button secondary" onClick={() => setEditing(true)}>
              <Pencil size={15} /> Change final pay
            </button>
          )
        ) : (
          <span className="muted">
            {editable ? "Manager access required" : "Cycle no longer editable"}
          </span>
        )}
      </td>
    </tr>
  );
}

export default function PayrollPage() {
  const [cycles, setCycles] = useState<Cycle[] | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [settings, setSettings] = useState<PayrollSetting | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [lines, setLines] = useState<PayrollLine[]>([]);
  const [showCycleForm, setShowCycleForm] = useState(false);
  const [editingCycle, setEditingCycle] = useState(false);
  const [exportsByType, setExportsByType] = useState<Record<string, PayrollExport>>({});
  const [busy, setBusy] = useState("");
  const [downloading, setDownloading] = useState<ReportFormat | "">("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const selected = cycles?.find((cycle) => cycle.id === selectedId) ?? null;
  const canManage = Boolean(me && canManagePayroll(me.role));
  const canOperate = Boolean(me && operatorRoles.has(me.role));
  const canApprove = Boolean(me && canApprovePayroll(me.role));
  const lineEditable = Boolean(selected && ["draft", "review"].includes(selected.status));

  const loadCycles = useCallback(async () => {
    const items = await fetchAll<Cycle>("payroll-cycles/?page_size=100");
    setCycles(items);
    setSelectedId((current) =>
      current && items.some((cycle) => cycle.id === current)
        ? current
        : (items[0]?.id ?? ""),
    );
  }, []);

  const loadLines = useCallback(async () => {
    if (!selectedId) {
      setLines([]);
      return;
    }
    setLines(
      await fetchAll<PayrollLine>(
        `payroll-lines/?cycle=${selectedId}&page_size=250`,
      ),
    );
  }, [selectedId]);

  const loadExports = useCallback(async () => {
    if (!selectedId || !canApprove) {
      setExportsByType({});
      return;
    }
    const items = await fetchAll<PayrollExport>(
      `payroll-exports/?cycle=${selectedId}&page_size=20`,
    );
    setExportsByType(
      items.reduce<Record<string, PayrollExport>>((grouped, item) => {
        const current = grouped[item.export_type];
        if (!current || item.version > current.version) {
          grouped[item.export_type] = item;
        }
        return grouped;
      }, {}),
    );
  }, [canApprove, selectedId]);

  function rememberExport(item: PayrollExport) {
    setExportsByType((current) => {
      const existing = current[item.export_type];
      if (existing && existing.version > item.version) return current;
      return { ...current, [item.export_type]: item };
    });
  }

  useEffect(() => {
    Promise.all([
      apiFetch<Me>("auth/me/"),
      fetchAll<Cycle>("payroll-cycles/?page_size=100"),
    ])
      .then(([profile, items]) => {
        setMe(profile);
        setCycles(items);
        setSelectedId(items[0]?.id ?? "");
        if (canManagePayroll(profile.role)) {
          return apiFetch<PayrollSetting>("payroll-settings/").then(setSettings);
        }
      })
      .catch((caught) =>
        setError(caught instanceof Error ? caught.message : "Unable to load payroll."),
      );
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setLines([]);
      setExportsByType({});
      return;
    }
    fetchAll<PayrollLine>(`payroll-lines/?cycle=${selectedId}&page_size=250`)
      .then(setLines)
      .catch((caught) =>
        setError(caught instanceof Error ? caught.message : "Unable to load payroll lines."),
      );
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId || !canApprove) return;
    void loadExports().catch((caught) =>
      setError(caught instanceof Error ? caught.message : "Unable to load payroll exports."),
    );
  }, [canApprove, loadExports, selectedId]);

  useEffect(() => {
    if (!canApprove) return;
    const pending = Object.values(exportsByType).filter((item) =>
      ["pending", "processing"].includes(item.status),
    );
    if (!pending.length) return;
    const timer = window.setTimeout(() => {
      void Promise.all(
        pending.map(async (item) => {
          const refreshed = await apiFetch<PayrollExport>(`payroll-exports/${item.id}/`);
          rememberExport(refreshed);
        }),
      ).catch((caught) =>
        setError(caught instanceof Error ? caught.message : "Unable to refresh payroll exports."),
      );
    }, 3000);
    return () => window.clearTimeout(timer);
  }, [canApprove, exportsByType]);

  async function command(id: string, action: string) {
    setBusy(`${action}-${id}`);
    setError("");
    setNotice("");
    try {
      await apiFetch(`payroll-cycles/${id}/${action}/`, {
        method: "POST",
        body: JSON.stringify(
          action === "approve"
            ? { below_contract_reason: "Reviewed and approved by finance." }
            : {},
        ),
      });
      await loadCycles();
      await loadLines();
      setNotice(`Payroll cycle ${action} completed.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Action failed.");
    } finally {
      setBusy("");
    }
  }

  async function savePolicy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!settings) return;
    const form = new FormData(event.currentTarget);
    setBusy("policy");
    setError("");
    try {
      const updated = await apiFetch<PayrollSetting>(
        `payroll-settings/${settings.id}/`,
        {
          method: "PATCH",
          body: JSON.stringify({
            half_day_deduction_percentage: form.get("half_day_percentage"),
          }),
        },
      );
      setSettings(updated);
      setNotice("Half-day payroll policy updated.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to save policy.");
    } finally {
      setBusy("");
    }
  }

  async function saveCycle(event: FormEvent<HTMLFormElement>, cycle?: Cycle) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(cycle ? `edit-${cycle.id}` : "create-cycle");
    setError("");
    try {
      await apiFetch(cycle ? `payroll-cycles/${cycle.id}/` : "payroll-cycles/", {
        method: cycle ? "PATCH" : "POST",
        body: JSON.stringify({
          name: form.get("name"),
          period_start: form.get("period_start"),
          period_end: form.get("period_end"),
        }),
      });
      await loadCycles();
      setShowCycleForm(false);
      setEditingCycle(false);
      setNotice(cycle ? "Payroll cycle updated." : "Payroll cycle created.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to save cycle.");
    } finally {
      setBusy("");
    }
  }

  if (error && !cycles) return <ErrorState message={error} />;
  if (!cycles || !me) return <LoadingState label="Loading payroll controls..." />;

  return (
    <>
      <header className="page-head">
        <div>
          <p className="eyebrow">Controlled close</p>
          <h1>Payroll</h1>
          <p>Calculate wages, review exceptions, and preserve every manual decision.</p>
        </div>
        {canManage && (
          <button className="button" onClick={() => setShowCycleForm((value) => !value)}>
            <Plus size={17} /> Create cycle
          </button>
        )}
      </header>

      {error && <p className="sync-banner payroll-error">{error}</p>}
      {notice && <p className="sync-banner payroll-notice">{notice}</p>}

      {canManage && settings && (
        <form className="card payroll-policy" onSubmit={savePolicy}>
          <div>
            <span className="settings-icon"><Settings2 size={19} /></span>
            <div>
              <strong>Half-day deduction policy</strong>
              <p>
                Applied to future half-day attendance decisions. Existing reviewed days keep
                their recorded percentage.
              </p>
            </div>
          </div>
          <div className="policy-control">
            <div className="money-input percentage-input">
              <input
                defaultValue={settings.half_day_deduction_percentage}
                max="100"
                min="0"
                name="half_day_percentage"
                required
                step="0.01"
                type="number"
              />
              <span>% cut</span>
            </div>
            <button className="button" disabled={busy === "policy"}>
              <Save size={15} /> Save default
            </button>
          </div>
        </form>
      )}

      {showCycleForm && (
        <form className="card cycle-form" onSubmit={(event) => saveCycle(event)}>
          <div className="field">
            <label htmlFor="cycle-name">Cycle name</label>
            <input id="cycle-name" name="name" placeholder="June 2026" required />
          </div>
          <div className="field">
            <label htmlFor="cycle-start">Period start</label>
            <input id="cycle-start" name="period_start" required type="date" />
          </div>
          <div className="field">
            <label htmlFor="cycle-end">Period end</label>
            <input id="cycle-end" name="period_end" required type="date" />
          </div>
          <button className="button" disabled={busy === "create-cycle"}>
            Create payroll cycle
          </button>
        </form>
      )}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Cycle</th>
              <th>Readiness</th>
              <th>Workers</th>
              <th>Net payroll</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {cycles.map((cycle) => (
              <tr className={selectedId === cycle.id ? "selected-row" : ""} key={cycle.id}>
                <td>
                  <button className="table-link" onClick={() => setSelectedId(cycle.id)}>
                    {cycle.name}
                  </button>
                  <br />
                  <span className="muted">
                    {cycle.period_start} to {cycle.period_end}
                  </span>
                </td>
                <td>
                  <div className="progress">
                    <span style={{ width: `${cycle.readiness_snapshot?.score ?? 0}%` }} />
                  </div>
                </td>
                <td>{cycle.line_count}</td>
                <td>AED {money(cycle.total_net_pay)}</td>
                <td><Badge value={cycle.status} /></td>
                <td>
                  <div className="inline-actions">
                    <button
                      className="button secondary"
                      onClick={() => setSelectedId(cycle.id)}
                    >
                      Review
                    </button>
                    {canOperate && ["draft", "review"].includes(cycle.status) && (
                      <button
                        className="button secondary"
                        disabled={busy === `build-${cycle.id}`}
                        onClick={() => command(cycle.id, "build")}
                      >
                        <PlayCircle size={15} /> Build
                      </button>
                    )}
                    {canApprove && cycle.status === "review" && (
                      <button
                        className="button secondary"
                        disabled={busy === `approve-${cycle.id}`}
                        onClick={() => command(cycle.id, "approve")}
                      >
                        <CheckCircle2 size={15} /> Approve
                      </button>
                    )}
                    {canApprove && cycle.status === "approved" && (
                      <button
                        className="button secondary"
                        disabled={busy === `lock-${cycle.id}`}
                        onClick={() => command(cycle.id, "lock")}
                      >
                        <LockKeyhole size={15} /> Lock
                      </button>
                    )}
                    {canApprove && ["locked", "exported"].includes(cycle.status) && (
                      <button
                        className="button secondary"
                        disabled={busy === `export-${cycle.id}`}
                        onClick={() => command(cycle.id, "export")}
                      >
                        <FileDown size={15} /> Export
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected && (
        <section className="payroll-lines">
          <div className="page-head payroll-section-head">
            <div>
              <p className="eyebrow">Worker breakdown</p>
              <h2>{selected.name}</h2>
              <p>Calculated pay remains visible beside any authorized final-pay override.</p>
            </div>
            <div className="inline-actions">
              {lines.length > 0 && (
                <>
                  <a
                    className="button secondary"
                    href={`/api/backend/payroll-cycles/${selected.id}/report-html/`}
                    rel="noreferrer"
                    target="_blank"
                  >
                    <Eye size={15} /> View HTML
                  </a>
                  <a
                    className="button secondary"
                    download
                    href={`/api/backend/payroll-cycles/${selected.id}/report-pdf/`}
                  >
                    <FileText size={15} /> PDF
                  </a>
                  <a
                    className="button secondary"
                    download
                    href={`/api/backend/payroll-cycles/${selected.id}/report-excel/`}
                  >
                    <FileSpreadsheet size={15} /> Excel
                  </a>
                </>
              )}
              {canManage && selected.status === "draft" && (
                <button
                  className="button secondary"
                  onClick={() => setEditingCycle((value) => !value)}
                >
                  <Pencil size={15} /> Edit cycle
                </button>
              )}
            </div>
          </div>

          {editingCycle && (
            <form className="card cycle-form" onSubmit={(event) => saveCycle(event, selected)}>
              <div className="field">
                <label htmlFor="edit-cycle-name">Cycle name</label>
                <input
                  defaultValue={selected.name}
                  id="edit-cycle-name"
                  name="name"
                  required
                />
              </div>
              <div className="field">
                <label htmlFor="edit-cycle-start">Period start</label>
                <input
                  defaultValue={selected.period_start}
                  id="edit-cycle-start"
                  name="period_start"
                  required
                  type="date"
                />
              </div>
              <div className="field">
                <label htmlFor="edit-cycle-end">Period end</label>
                <input
                  defaultValue={selected.period_end}
                  id="edit-cycle-end"
                  name="period_end"
                  required
                  type="date"
                />
              </div>
              <button className="button" disabled={busy === `edit-${selected.id}`}>
                Save cycle
              </button>
            </form>
          )}

          {lines.length ? (
            <div className="table-wrap">
              <table className="payroll-line-table">
                <thead>
                  <tr>
                    <th>Worker</th>
                    <th>Contract basic</th>
                    <th>Gross</th>
                    <th>Calculated net</th>
                    <th>Final net</th>
                    <th>Adjustment</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((line) => (
                    <LineEditor
                      canManage={canManage}
                      editable={lineEditable}
                      key={`${line.id}-${line.net_pay}-${line.manual_net_pay ?? "calculated"}`}
                      line={line}
                      onSaved={async () => {
                        await loadLines();
                        await loadCycles();
                        setNotice(`${line.worker_name}'s final pay was updated.`);
                      }}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="card empty payroll-empty">
              <p>Build this cycle to generate individual worker salary lines.</p>
              {canOperate && ["draft", "review"].includes(selected.status) && (
                <button
                  className="button"
                  disabled={busy === `build-${selected.id}`}
                  onClick={() => command(selected.id, "build")}
                >
                  <PlayCircle size={17} />
                  {busy === `build-${selected.id}` ? "Building payroll..." : "Build cycle"}
                </button>
              )}
            </div>
          )}
        </section>
      )}
    </>
  );
}
