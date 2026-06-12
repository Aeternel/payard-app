"use client";

import { ArrowRight, ShieldCheck } from "lucide-react";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          phone: form.get("phone"),
          password: form.get("password"),
        }),
      });
      const body = await response.text();
      let data: {
        error?: {
          detail?: string | { non_field_errors?: string[] };
        };
      } = {};
      try {
        data = body ? JSON.parse(body) : {};
      } catch {
        setError("The server returned an invalid response. Please try again.");
        return;
      }
      if (!response.ok) {
        const detail = data.error?.detail;
        setError(
          typeof detail === "string"
            ? detail
            : detail?.non_field_errors?.[0] ?? "Unable to sign in.",
        );
        return;
      }
      const destination = new URLSearchParams(window.location.search).get("next");
      router.replace(
        (destination?.startsWith("/app") ? destination : "/app") as Route,
      );
      router.refresh();
    } catch {
      setError("Unable to reach PayYard. Please check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-story">
        <div className="brand"><span className="brand-mark">P</span> PayYard</div>
        <div>
          <p className="eyebrow">Payroll control for deskless teams</p>
          <h1>From the site gate to payroll close.</h1>
          <p>Capture attendance, resolve exceptions, approve overtime, and prepare WPS-ready wages with a defensible record behind every dirham.</p>
        </div>
        <p><ShieldCheck size={18} style={{ verticalAlign: "middle", marginRight: 8 }} /> Tenant-isolated access, immutable audit events, and explicit payroll approvals.</p>
      </section>
      <section className="auth-panel">
        <form className="auth-card" onSubmit={login}>
          <p className="eyebrow">Secure workspace</p>
          <h2>Welcome back</h2>
          <p>Enter your phone number and password. We will open your assigned company and sites.</p>
          <div className="field">
            <label htmlFor="phone">Phone number</label>
            <input id="phone" name="phone" type="tel" placeholder="+971 50 123 4567" required />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input id="password" name="password" type="password" minLength={12} required />
          </div>
          {error && <p className="error">{error}</p>}
          <button className="button full" disabled={loading}>
            {loading ? "Signing in..." : "Sign in"} <ArrowRight size={17} />
          </button>
        </form>
      </section>
    </main>
  );
}
