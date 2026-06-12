"use client";

import { Plus, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge, ErrorState, LoadingState } from "@/components/page-state";
import { fetchAll } from "@/lib/api";

type Membership = {
  id: string;
  role: string;
  is_active: boolean;
  payroll_profile_id: string | null;
  user: {
    id: string;
    name: string;
    phone: string;
    email: string;
    is_active: boolean;
  };
};

export default function TeamPage() {
  const [members, setMembers] = useState<Membership[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchAll<Membership>("memberships/?page_size=200")
      .then(setMembers)
      .catch((caught) =>
        setError(caught instanceof Error ? caught.message : "Unable to load team access."),
      );
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!members) return <LoadingState label="Loading team access..." />;

  return (
    <>
      <header className="page-head">
        <div>
          <p className="eyebrow">Access governance</p>
          <h1>Team access</h1>
          <p>Manage company logins separately from employee payroll identities.</p>
        </div>
        <Link className="button" href="/app/team/new">
          <Plus size={17} /> Onboard staff
        </Link>
      </header>

      <div className="sync-banner">
        <span>
          <ShieldCheck size={16} /> Owners and Admins onboard staff accounts. HR manages
          workers, but cannot grant privileged company access.
        </span>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Team member</th>
              <th>Role</th>
              <th>Login</th>
              <th>Payroll profile</th>
              <th>Access</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {members.map((member) => (
              <tr key={member.id}>
                <td>
                  <strong>{member.user.name}</strong>
                  <br />
                  <span className="muted">{member.user.email || "No email"}</span>
                </td>
                <td><Badge value={member.role} /></td>
                <td>{member.user.phone}</td>
                <td>
                  <Badge value={member.payroll_profile_id ? "linked" : "not_linked"} />
                </td>
                <td><Badge value={member.is_active && member.user.is_active ? "active" : "inactive"} /></td>
                <td>
                  {!member.payroll_profile_id ? (
                    <Link
                      className="button secondary"
                      href={`/app/team/${member.id}/payroll`}
                    >
                      Add payroll profile
                    </Link>
                  ) : (
                    <span className="muted">Payroll linked</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
