"use client";

import {
  CheckCircle2,
  CloudOff,
  CalendarDays,
  CircleDotDashed,
  LogOut,
  RefreshCw,
  SearchCheck,
  UserCheck,
  X,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge, ErrorState, LoadingState } from "@/components/page-state";
import { apiFetch, fetchAll } from "@/lib/api";
import {
  clearQueuedAttendance,
  queueAttendance,
  queuedAttendance,
} from "@/lib/offline";
import type { Attendance, Roster, Worker } from "@/lib/types";

type AttendanceException = {
  id: string;
  attendance: string;
  exception_type: string;
  reason: string;
  evidence: Record<string, unknown>;
  status: string;
};

function deviceId() {
  const key = "payyard-device-id";
  const existing = localStorage.getItem(key);
  if (existing) return existing;
  const created = crypto.randomUUID();
  localStorage.setItem(key, created);
  return created;
}

function time(value: string | null) {
  if (!value) return "Not recorded";
  return new Date(value).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function AttendancePage() {
  const today = new Date().toISOString().slice(0, 10);
  const [rosters, setRosters] = useState<Roster[] | null>(null);
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [attendance, setAttendance] = useState<Attendance[]>([]);
  const [exceptions, setExceptions] = useState<AttendanceException[]>([]);
  const [queued, setQueued] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [decisionNotes, setDecisionNotes] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    const [r, w, a, e, q] = await Promise.all([
      fetchAll<Roster>(`rosters/?date=${today}&status=scheduled&page_size=200`),
      fetchAll<Worker>("workers/?status=active&page_size=200"),
      fetchAll<Attendance>(`attendance/?work_date=${today}&page_size=200`),
      fetchAll<AttendanceException>(
        "attendance-exceptions/?status=open&page_size=200",
      ),
      queuedAttendance(),
    ]);
    setRosters(r);
    setWorkers(w);
    setAttendance(a);
    setExceptions(e);
    setQueued(q.length);
  }, [today]);

  useEffect(() => {
    queueMicrotask(() => {
      void load().catch((caught) =>
        setError(caught instanceof Error ? caught.message : "Unable to load attendance."),
      );
    });
  }, [load]);

  const workerMap = useMemo(
    () => new Map(workers.map((worker) => [worker.id, worker])),
    [workers],
  );
  const attendanceByWorker = useMemo(
    () => new Map(attendance.map((item) => [item.worker, item])),
    [attendance],
  );
  const exceptionsByAttendance = useMemo(() => {
    const grouped = new Map<string, AttendanceException[]>();
    for (const item of exceptions) {
      grouped.set(item.attendance, [...(grouped.get(item.attendance) ?? []), item]);
    }
    return grouped;
  }, [exceptions]);
  const reviewing = attendance.find((item) => item.id === reviewingId) ?? null;
  const reviewExceptions = reviewing
    ? exceptionsByAttendance.get(reviewing.id) ?? []
    : [];

  async function checkIn(roster: Roster) {
    setBusy(roster.id);
    setError("");
    const payload = {
      roster_assignment: roster.id,
      captured_at: new Date().toISOString(),
      verification_method: "id",
      device_id: deviceId(),
      idempotency_key: crypto.randomUUID(),
    };
    try {
      if (!navigator.onLine) throw new Error("offline");
      await apiFetch("attendance/check_in/", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      await load();
    } catch (caught) {
      if (!navigator.onLine || (caught instanceof Error && caught.message === "offline")) {
        await queueAttendance(payload);
        setQueued((value) => value + 1);
      } else {
        setError(caught instanceof Error ? caught.message : "Attendance failed.");
      }
    } finally {
      setBusy("");
    }
  }

  async function checkOut(record: Attendance) {
    setBusy(`checkout-${record.id}`);
    setError("");
    try {
      await apiFetch(`attendance/${record.id}/check_out/`, {
        method: "POST",
        body: JSON.stringify({
          captured_at: new Date().toISOString(),
          notes: "Checkout captured from supervisor attendance screen.",
        }),
      });
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Checkout failed.");
    } finally {
      setBusy("");
    }
  }

  async function decide(
    item: AttendanceException,
    outcome: "full_day" | "half_day" | "rejected",
  ) {
    const reason = decisionNotes[item.id]?.trim() ?? "";
    if (reason.length < 3) {
      setError("Add a short reason before choosing an attendance outcome.");
      return;
    }
    setBusy(`decision-${item.id}`);
    setError("");
    try {
      await apiFetch(`attendance-exceptions/${item.id}/decide/`, {
        method: "POST",
        body: JSON.stringify({ outcome, reason }),
      });
      if (reviewExceptions.length <= 1) setReviewingId(null);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Decision failed.");
    } finally {
      setBusy("");
    }
  }

  async function sync() {
    const records = await queuedAttendance();
    if (!records.length) return;
    const result = await apiFetch<{
      results: { idempotency_key: string; error?: string }[];
    }>("attendance/sync/", {
      method: "POST",
      body: JSON.stringify({ records }),
    });
    const successful = result.results
      .filter((item) => !item.error)
      .map((item) => item.idempotency_key);
    await clearQueuedAttendance(successful);
    await load();
  }

  if (error && !rosters) return <ErrorState message={error} />;
  if (!rosters) return <LoadingState label="Loading today’s roster..." />;

  return (
    <>
      <header className="page-head">
        <div>
          <p className="eyebrow">Supervisor mode</p>
          <h1>Today&apos;s attendance</h1>
          <p>Capture shifts, check workers out, and decide attendance exceptions.</p>
        </div>
        <button className="button secondary" onClick={sync}>
          <RefreshCw size={17} /> Sync now
        </button>
      </header>

      {queued > 0 && (
        <div className="sync-banner">
          <span>
            <CloudOff size={16} style={{ verticalAlign: "middle", marginRight: 6 }} />
            {queued} encrypted attendance record{queued > 1 ? "s" : ""} waiting to sync.
          </span>
          <button onClick={sync}>Retry</button>
        </div>
      )}
      {error && <p className="error">{error}</p>}

      <div className="toolbar">
        <CalendarDays size={18} />
        <strong>{today}</strong>
        <span style={{ color: "var(--muted)" }}>{rosters.length} workers scheduled</span>
      </div>

      <section className="quick-grid">
        {rosters.map((roster) => {
          const worker = workerMap.get(roster.worker);
          const record = attendanceByWorker.get(roster.worker);
          const recordExceptions = record
            ? exceptionsByAttendance.get(record.id) ?? []
            : [];
          const canCheckOut =
            record
            && !record.check_out_at
            && ["open", "pending"].includes(record.status);

          return (
            <article className="worker-tile" key={roster.id}>
              <h3>{worker?.full_name ?? "Worker"}</h3>
              <p>
                {worker?.worker_code} · {worker?.job_title || "Site worker"}
              </p>
              {record ? (
                <>
                  <Badge value={record.status} />
                  {record.outcome === "half_day" && <Badge value="half_day" />}
                  <p style={{ marginTop: ".7rem" }}>
                    In: {time(record.check_in_at)}
                    {record.check_out_at ? ` · Out: ${time(record.check_out_at)}` : ""}
                  </p>
                  <div className="worker-actions">
                    {recordExceptions.length > 0 && (
                      <button
                        className="button secondary"
                        onClick={() => setReviewingId(record.id)}
                      >
                        <SearchCheck size={16} /> Review {recordExceptions.length}
                      </button>
                    )}
                    {canCheckOut && (
                      <button
                        className="button"
                        disabled={busy === `checkout-${record.id}`}
                        onClick={() => checkOut(record)}
                      >
                        <LogOut size={16} />
                        {busy === `checkout-${record.id}` ? "Checking out..." : "Check out"}
                      </button>
                    )}
                  </div>
                </>
              ) : (
                <div className="worker-actions">
                  <button
                    className="button"
                    disabled={busy === roster.id}
                    onClick={() => checkIn(roster)}
                  >
                    <UserCheck size={17} />
                    {busy === roster.id ? "Capturing..." : "Check in"}
                  </button>
                </div>
              )}
            </article>
          );
        })}
      </section>

      {reviewing && (
        <div className="modal-backdrop" role="presentation">
          <section
            className="review-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="review-title"
          >
            <div className="review-head">
              <div>
                <p className="eyebrow">Attendance review</p>
                <h2 id="review-title">{reviewing.worker_name}</h2>
                <p>
                  {reviewing.worker_code} · {reviewing.site_name} · In {time(reviewing.check_in_at)}
                </p>
              </div>
              <button
                className="icon-button"
                aria-label="Close review"
                onClick={() => setReviewingId(null)}
              >
                <X size={20} />
              </button>
            </div>

            <div className="review-summary">
              <Badge value={reviewing.status} />
              <span>
                Choose how this time exception should affect attendance and payroll.
              </span>
            </div>

            <div className="exception-list">
              {reviewExceptions.map((item) => (
                <article className="exception-card" key={item.id}>
                  <div>
                    <strong>{item.exception_type.replaceAll("_", " ")}</strong>
                    <p>{item.reason}</p>
                  </div>
                  <div className="field">
                    <label htmlFor={`reason-${item.id}`}>Decision note</label>
                    <textarea
                      id={`reason-${item.id}`}
                      rows={3}
                      value={decisionNotes[item.id] ?? ""}
                      placeholder="Example: Bus delay accepted by site supervisor."
                      onChange={(event) =>
                        setDecisionNotes((current) => ({
                          ...current,
                          [item.id]: event.target.value,
                        }))
                      }
                    />
                  </div>
                  <div className="decision-actions">
                    <button
                      className="button secondary"
                      disabled={busy === `decision-${item.id}`}
                      onClick={() => decide(item, "full_day")}
                    >
                      <CheckCircle2 size={16} /> Accept full day
                    </button>
                    <button
                      className="button secondary"
                      disabled={busy === `decision-${item.id}`}
                      onClick={() => decide(item, "half_day")}
                    >
                      <CircleDotDashed size={16} /> Mark half day
                    </button>
                    <button
                      className="button danger"
                      disabled={busy === `decision-${item.id}`}
                      onClick={() => decide(item, "rejected")}
                    >
                      <XCircle size={16} /> Reject attendance
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </div>
      )}
    </>
  );
}
