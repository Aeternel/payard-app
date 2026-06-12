"use client";

import {
  Banknote,
  Bell,
  Building2,
  CalendarDays,
  ClipboardCheck,
  FileWarning,
  Gauge,
  HandCoins,
  LogOut,
  Menu,
  MessageSquareWarning,
  ReceiptText,
  UserCog,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import type { Me } from "@/lib/types";

const navigation = [
  ["/app", "Overview", Gauge],
  ["/app/workers", "Workers", Users],
  ["/app/sites", "Sites & roster", Building2],
  ["/app/attendance", "Attendance", ClipboardCheck],
  ["/app/payroll", "Payroll", Banknote],
  ["/app/my-payroll", "My payroll", ReceiptText],
  ["/app/advances", "Advances", HandCoins],
  ["/app/disputes", "Disputes", MessageSquareWarning],
  ["/app/compliance", "Compliance", FileWarning],
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    apiFetch<Me>("auth/me/").then(setMe).catch(() => router.replace("/login"));
  }, [router]);

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.replace("/login");
    router.refresh();
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link href="/app" className="brand"><span className="brand-mark">P</span> PayYard</Link>
        <nav className="nav">
          {navigation.map(([href, label, Icon]) => {
            const active = href === "/app" ? pathname === href : pathname.startsWith(href);
            return <Link key={href} href={href} className={active ? "active" : ""}><Icon size={18} />{label}</Link>;
          })}
          {me && ["admin", "owner"].includes(me.role) && (
            <Link
              href="/app/team"
              className={pathname.startsWith("/app/team") ? "active" : ""}
            >
              <UserCog size={18} /> Team access
            </Link>
          )}
        </nav>
        <div className="sidebar-footer">
          <div style={{ fontSize: ".85rem", fontWeight: 600 }}>{me?.name ?? "Loading..."}</div>
          <div style={{ fontSize: ".72rem", color: "#9fb8ac", margin: ".2rem 0 .8rem" }}>{me?.company.name} · {me?.role}</div>
          <button className="button secondary full" onClick={logout}><LogOut size={16} /> Sign out</button>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div style={{ display: "flex", alignItems: "center", gap: ".6rem", fontWeight: 600 }}><Menu size={19} /> Operations workspace</div>
          <div style={{ display: "flex", gap: ".65rem" }}>
            <button className="button secondary" aria-label="Notifications"><Bell size={17} /></button>
            <Link className="button" href="/app/attendance"><CalendarDays size={17} /> Today&apos;s roster</Link>
          </div>
        </header>
        <div className="content">{children}</div>
      </main>
    </div>
  );
}
