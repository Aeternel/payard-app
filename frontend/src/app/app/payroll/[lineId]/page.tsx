"use client";

import { ArrowLeft, CalendarDays } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge, ErrorState, LoadingState } from "@/components/page-state";
import { apiFetch } from "@/lib/api";

type BreakdownEntry = {
  date: string;
  site_name: string;
  shift_name: string;
  day_type: string;
  attendance_status: string;
  check_in_at: string | null;
  check_out_at: string | null;
  payable_fraction: string;
  expected_pay: string;
  regular_pay: string;
  overtime_pay: string;
  allowances: string;
  posted_deductions: string;
  earned_amount: string;
  pay_impact: string;
  running_total: string;
  reason: string;
  ledger_status: string;
};

type Breakdown = {
  line: {
    id: string;
    cycle_name: string;
    period_start: string;
    period_end: string;
    cycle_status: string;
    worker_name: string;
    worker_code: string;
    job_title: string;
    wage_type: string;
    contract_basic: string;
    calculated_net_pay: string;
    final_net_pay: string;
    manual_net_pay: string | null;
    manual_override_reason: string;
  };
  summary: {
    scheduled_days: number;
    full_days: number;
    half_days: number;
    absent_or_rejected_days: number;
    daily_earned_total: string;
    scheduled_pay_not_earned: string;
    overtime_total: string;
  };
  entries: BreakdownEntry[];
};

function money(value: string) {
  return Number(value).toLocaleString("en-AE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function time(value: string | null) {
  if (!value) return "Not recorded";
  return new Date(value).toLocaleTimeString("en-AE", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function dateLabel(value: string) {
  return new Date(`${value}T00:00:00`).toLocaleDateString("en-AE", {
    weekday: "short",
    day: "2-digit",
    month: "short",
  });
}

export default function PayrollWorkerDetailPage() {
  const params = useParams<{ lineId: string }>();
  const [data, setData] = useState<Breakdown | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<Breakdown>(`payroll-lines/${params.lineId}/daily-breakdown/`)
      .then(setData)
      .catch((caught) =>
        setError(caught instanceof Error ? caught.message : "Unable to load payroll detail."),
      );
  }, [params.lineId]);

  if (error) return <ErrorState message={error} />;
  if (!data) return <LoadingState label="Loading daily salary breakdown..." />;

  return (
    <>
      <Link className="button secondary detail-back" href="/app/payroll">
        <ArrowLeft size={16} /> Back to payroll
      </Link>

      <header className="page-head payroll-detail-head">
        <div>
          <p className="eyebrow">Daily salary detail</p>
          <h1>{data.line.worker_name}</h1>
          <p className="payroll-detail-meta">
            {data.line.worker_code}
            {data.line.job_title ? ` · ${data.line.job_title}` : ""}
            {" · "}
            {data.line.cycle_name} ({data.line.period_start} to {data.line.period_end})
          </p>
        </div>
        <Badge value={data.line.cycle_status} />
      </header>

      <section className="grid payroll-detail-stats">
        <div className="card stat payroll-detail-stat">
          <div className="label">Scheduled days</div>
          <div className="value">{data.summary.scheduled_days}</div>
          <div className="hint">{data.summary.full_days} full days</div>
        </div>
        <div className="card stat payroll-detail-stat">
          <div className="label">Half days</div>
          <div className="value">{data.summary.half_days}</div>
          <div className="hint">Based on recorded decisions</div>
        </div>
        <div className="card stat payroll-detail-stat">
          <div className="label">Absent / rejected</div>
          <div className="value">{data.summary.absent_or_rejected_days}</div>
          <div className="hint">No payable daily ledger</div>
        </div>
        <div className="card stat payroll-detail-stat">
          <div className="label">Daily earned</div>
          <div className="value">AED {money(data.summary.daily_earned_total)}</div>
          <div className="hint">Includes approved overtime</div>
        </div>
        <div className="card stat payroll-detail-stat">
          <div className="label">Pay impact</div>
          <div className="value">AED {money(data.summary.scheduled_pay_not_earned)}</div>
          <div className="hint">Scheduled pay not earned</div>
        </div>
      </section>

      <div className="sync-banner payroll-detail-note">
        <span>
          <CalendarDays size={16} /> Pay impact compares each scheduled day with its normal
          full-day value. Pending attendance is not treated as a deduction until reviewed.
        </span>
      </div>

      <div className="table-wrap">
        <table className="payroll-detail-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Attendance</th>
              <th>Site & time</th>
              <th>Expected</th>
              <th>Earned components</th>
              <th>Earned</th>
              <th>Pay impact</th>
              <th>Running total</th>
            </tr>
          </thead>
          <tbody>
            {data.entries.map((entry) => (
              <tr key={entry.date}>
                <td><strong>{dateLabel(entry.date)}</strong></td>
                <td>
                  <Badge value={entry.day_type} />
                  <br />
                  <span className="muted">
                    {Math.round(Number(entry.payable_fraction) * 100)}% payable
                  </span>
                  {entry.reason && (
                    <>
                      <br />
                      <span className="muted">{entry.reason}</span>
                    </>
                  )}
                </td>
                <td>
                  <div className="day-context">
                    <strong>{entry.site_name}</strong>
                    <span>{entry.shift_name}</span>
                    <span>{time(entry.check_in_at)} to {time(entry.check_out_at)}</span>
                  </div>
                </td>
                <td>AED {money(entry.expected_pay)}</td>
                <td>
                  <div className="day-pay-components">
                    <strong>Base: AED {money(entry.regular_pay)}</strong>
                    <span>Allowance: AED {money(entry.allowances)}</span>
                    <span>Overtime: AED {money(entry.overtime_pay)}</span>
                    {Number(entry.posted_deductions) > 0 && (
                      <span>Posted deduction: AED {money(entry.posted_deductions)}</span>
                    )}
                  </div>
                </td>
                <td className="amount-positive">+ AED {money(entry.earned_amount)}</td>
                <td className={Number(entry.pay_impact) > 0 ? "amount-negative" : ""}>
                  {Number(entry.pay_impact) > 0
                    ? `- AED ${money(entry.pay_impact)}`
                    : "AED 0.00"}
                </td>
                <td><strong>AED {money(entry.running_total)}</strong></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!data.entries.length && (
        <div className="card empty">No scheduled roster days exist inside this cycle.</div>
      )}

      <section className="card payroll-reconciliation">
        <div>
          <span>Contract basic</span>
          <strong>AED {money(data.line.contract_basic)}</strong>
        </div>
        <div>
          <span>Cycle calculated net</span>
          <strong>AED {money(data.line.calculated_net_pay)}</strong>
        </div>
        <div>
          <span>Final net</span>
          <strong>AED {money(data.line.final_net_pay)}</strong>
          {data.line.manual_net_pay !== null && (
            <p className="muted">
              Manual override: {data.line.manual_override_reason || "No reason recorded"}
            </p>
          )}
        </div>
      </section>
    </>
  );
}
