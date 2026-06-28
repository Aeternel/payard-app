"use client";

import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Badge, ErrorState, LoadingState } from "@/components/page-state";
import { apiFetch, fetchAll } from "@/lib/api";
import { canRunComplianceScan } from "@/lib/access";
import type { Me } from "@/lib/types";

type Alert = {
  id: string;
  title: string;
  description: string;
  alert_type: string;
  severity: string;
  status: string;
  occurrence_date: string;
};

export default function CompliancePage() {
  const [items, setItems] = useState<Alert[] | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    const [profile, alerts] = await Promise.all([
      apiFetch<Me>("auth/me/"),
      fetchAll<Alert>("compliance-alerts/?page_size=100"),
    ]);
    setMe(profile);
    setItems(alerts);
  }, []);

  useEffect(() => {
    queueMicrotask(() => {
      void load().catch((caught) =>
        setError(caught instanceof Error ? caught.message : "Unable to load compliance alerts."),
      );
    });
  }, [load]);

  async function scan() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await apiFetch<{ detail: string }>("compliance-alerts/scan/", {
        method: "POST",
        body: "{}",
      });
      setNotice(response.detail);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to queue compliance scan.");
    } finally {
      setBusy(false);
    }
  }

  if (error && !items) return <ErrorState message={error} />;
  if (!items || !me) return <LoadingState label="Loading compliance controls..." />;

  return (
    <>
      <header className="page-head">
        <div>
          <p className="eyebrow">Compliance-aware controls</p>
          <h1>Alerts</h1>
          <p>
            Operational signals for UAE work-hour, heat, consent, and payroll risks.
            Legal validation remains required before launch.
          </p>
        </div>
        {canRunComplianceScan(me.role) && (
          <button className="button secondary" disabled={busy} onClick={scan}>
            <RefreshCw size={17} /> {busy ? "Queuing scan..." : "Run scan"}
          </button>
        )}
      </header>

      {error && <p className="sync-banner payroll-error">{error}</p>}
      {notice && <p className="sync-banner payroll-notice">{notice}</p>}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Alert</th>
              <th>Type</th>
              <th>Date</th>
              <th>Severity</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>
                  <strong>{item.title}</strong>
                  <br />
                  <span style={{ color: "var(--muted)" }}>{item.description}</span>
                </td>
                <td>{item.alert_type.replaceAll("_", " ")}</td>
                <td>{item.occurrence_date}</td>
                <td><Badge value={item.severity} /></td>
                <td><Badge value={item.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
