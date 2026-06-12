export function LoadingState({ label = "Loading workspace..." }: { label?: string }) {
  return <div className="card empty">{label}</div>;
}

export function ErrorState({ message }: { message: string }) {
  return <div className="card empty"><strong>Something needs attention.</strong><p>{message}</p></div>;
}

export function Badge({ value }: { value: string }) {
  const good = [
    "active",
    "approved",
    "ready",
    "resolved",
    "locked",
    "paid",
    "linked",
  ].includes(value);
  const bad = ["absent", "rejected", "failed", "critical", "terminated"].includes(value);
  return <span className={`badge ${good ? "good" : bad ? "bad" : "warn"}`}>{value.replaceAll("_", " ")}</span>;
}
