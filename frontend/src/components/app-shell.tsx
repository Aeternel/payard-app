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
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import {
  canAccessAttendance,
  canManageTeam,
  canViewPayroll,
} from "@/lib/access";
import type { Me } from "@/lib/types";

type NavigationItem = {
  href: string;
  label: string;
  Icon: LucideIcon;
  visible?: (role: Me["role"]) => boolean;
};

const navigation: NavigationItem[] = [
  { href: "/app", label: "Overview", Icon: Gauge },
  { href: "/app/workers", label: "Workers", Icon: Users },
  { href: "/app/sites", label: "Sites & roster", Icon: Building2 },
  {
    href: "/app/attendance",
    label: "Attendance",
    Icon: ClipboardCheck,
    visible: canAccessAttendance,
  },
  {
    href: "/app/payroll",
    label: "Payroll",
    Icon: Banknote,
    visible: canViewPayroll,
  },
  { href: "/app/my-payroll", label: "My payroll", Icon: ReceiptText },
  { href: "/app/advances", label: "Advances", Icon: HandCoins },
  { href: "/app/disputes", label: "Disputes", Icon: MessageSquareWarning },
  { href: "/app/compliance", label: "Compliance", Icon: FileWarning },
];

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

  const navItems = me
    ? navigation.filter((item) => !item.visible || item.visible(me.role))
    : navigation.filter((item) => !item.visible);
  const quickLink = me
    ? canAccessAttendance(me.role)
      ? { href: "/app/attendance", label: "Today's roster", Icon: CalendarDays }
      : canViewPayroll(me.role)
        ? { href: "/app/payroll", label: "Payroll queue", Icon: Banknote }
        : null
    : null;
  const QuickLinkIcon = quickLink?.Icon;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link href="/app" className="brand"><span className="brand-mark">P</span> PayYard</Link>
        <nav className="nav">
          {navItems.map(({ href, label, Icon }) => {
            const active = href === "/app" ? pathname === href : pathname.startsWith(href);
            return <Link key={href} href={href} className={active ? "active" : ""}><Icon size={18} />{label}</Link>;
          })}
          {me && canManageTeam(me.role) && (
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
            {quickLink && QuickLinkIcon && (
              <Link className="button" href={quickLink.href}>
                <QuickLinkIcon size={17} /> {quickLink.label}
              </Link>
            )}
          </div>
        </header>
        <div className="content">{children}</div>
      </main>
    </div>
  );
}
