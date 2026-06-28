"use client";

import { Plus, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Badge, ErrorState, LoadingState } from "@/components/page-state";
import { apiFetch, fetchAll } from "@/lib/api";
import { canManageWorkers } from "@/lib/access";
import type { Me, Worker } from "@/lib/types";

export default function WorkersPage() {
  const [workers, setWorkers] = useState<Worker[] | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      fetchAll<Worker>("workers/?page_size=200"),
      apiFetch<Me>("auth/me/"),
    ])
      .then(([items, profile]) => {
        setWorkers(items);
        setMe(profile);
      })
      .catch((caught) =>
        setError(caught instanceof Error ? caught.message : "Unable to load workers."),
      );
  }, []);

  const shown = useMemo(
    () =>
      workers?.filter(
        (worker) =>
          `${worker.worker_code} ${worker.full_name} ${worker.phone}`
            .toLowerCase()
            .includes(query.toLowerCase()) &&
          (!status || worker.status === status),
      ) ?? [],
    [workers, query, status],
  );

  if (error) return <ErrorState message={error} />;
  if (!workers || !me) return <LoadingState label="Loading workers..." />;

  return (
    <>
      <header className="page-head">
        <div>
          <p className="eyebrow">Worker master</p>
          <h1>Workers</h1>
          <p>Employment, wage setup, documents, and payroll readiness.</p>
        </div>
        {canManageWorkers(me.role) && (
          <Link className="button" href="/app/workers/new">
            <Plus size={17} /> Add worker
          </Link>
        )}
      </header>
      <div className="toolbar">
        <Search size={18} />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search code, name, or phone"
        />
        <select value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="draft">Draft</option>
          <option value="suspended">Suspended</option>
          <option value="terminated">Terminated</option>
        </select>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Worker</th>
              <th>Role</th>
              <th>Wage setup</th>
              <th>Status</th>
              <th>Payroll</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((worker) => (
              <tr key={worker.id}>
                <td>
                  <strong>{worker.full_name}</strong>
                  <br />
                  <span className="muted">
                    {worker.worker_code} · {worker.phone || "No phone"}
                  </span>
                </td>
                <td>{worker.job_title || "Not set"}</td>
                <td>{worker.wage_type} · AED {worker.basic_wage}</td>
                <td><Badge value={worker.status} /></td>
                <td><Badge value={worker.payroll_ready ? "ready" : "incomplete"} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
