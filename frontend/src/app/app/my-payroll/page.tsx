"use client";

import { Banknote, LockKeyhole } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, ErrorState, LoadingState } from "@/components/page-state";
import { apiFetch } from "@/lib/api";

type Payslip = {
  id: string;
  cycle_name: string;
  period_start: string;
  period_end: string;
  cycle_status: string;
  contract_basic: string;
  regular_pay: string;
  overtime_pay: string;
  allowances: string;
  gross_pay: string;
  absence_deductions: string;
  advance_deductions: string;
  other_deductions: string;
  net_pay: string;
};

type MyPayroll = {
  profile: {
    worker_code: string;
    full_name: string;
    job_title: string;
    department: string;
    basic_wage: string;
    currency: string;
  } | null;
  payslips: Payslip[];
};

function money(value: string) {
  return Number(value).toLocaleString("en-AE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export default function MyPayrollPage() {
  const [data, setData] = useState<MyPayroll | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<MyPayroll>("auth/my-payroll/")
      .then(setData)
      .catch((caught) =>
        setError(caught instanceof Error ? caught.message : "Unable to load your payroll."),
      );
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!data) return <LoadingState label="Loading your payroll..." />;

  return (
    <>
      <header className="page-head">
        <div>
          <p className="eyebrow">Private payroll</p>
          <h1>My payroll</h1>
          <p>Only finalized payroll cycles linked to your own account appear here.</p>
        </div>
        <LockKeyhole size={24} />
      </header>

      {!data.profile ? (
        <div className="card empty">
          <Banknote size={28} />
          <h2>No payroll profile linked</h2>
          <p>
            Your login has company access, but it is not linked to an employee payroll
            profile. An Owner or Admin can add this through Team Access.
          </p>
        </div>
      ) : (
        <>
          <section className="card staff-payroll-profile">
            <div>
              <p className="eyebrow">{data.profile.department || "Staff employee"}</p>
              <h2>{data.profile.full_name}</h2>
              <p>{data.profile.worker_code} · {data.profile.job_title || "Role not set"}</p>
            </div>
            <div>
              <span>Contract basic</span>
              <strong>{data.profile.currency} {money(data.profile.basic_wage)}</strong>
            </div>
          </section>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Payroll cycle</th>
                  <th>Regular</th>
                  <th>Overtime</th>
                  <th>Allowances</th>
                  <th>Deductions</th>
                  <th>Final net</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.payslips.map((line) => (
                  <tr key={line.id}>
                    <td>
                      <strong>{line.cycle_name}</strong>
                      <br />
                      <span className="muted">{line.period_start} to {line.period_end}</span>
                    </td>
                    <td>AED {money(line.regular_pay)}</td>
                    <td>AED {money(line.overtime_pay)}</td>
                    <td>AED {money(line.allowances)}</td>
                    <td>
                      AED {money(String(
                        Number(line.absence_deductions)
                        + Number(line.advance_deductions)
                        + Number(line.other_deductions),
                      ))}
                    </td>
                    <td><strong>AED {money(line.net_pay)}</strong></td>
                    <td><Badge value={line.cycle_status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!data.payslips.length && (
            <div className="card empty">
              No locked payslips are available yet. Draft and review payroll remains private
              to the payroll team.
            </div>
          )}
        </>
      )}
    </>
  );
}
