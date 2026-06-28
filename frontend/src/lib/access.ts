import type { Me } from "@/lib/types";

export type StaffRole = Me["role"];

function roleIn(role: StaffRole, allowed: readonly StaffRole[]) {
  return allowed.includes(role);
}

export function canAccessAttendance(role: StaffRole) {
  return roleIn(role, ["supervisor", "operations", "hr", "payroll", "admin", "owner"]);
}

export function canViewPayroll(role: StaffRole) {
  return roleIn(role, ["hr", "payroll", "finance", "admin", "owner"]);
}

export function canManagePayroll(role: StaffRole) {
  return roleIn(role, ["hr", "admin", "owner"]);
}

export function canApprovePayroll(role: StaffRole) {
  return roleIn(role, ["finance", "admin", "owner"]);
}

export function canManageWorkers(role: StaffRole) {
  return roleIn(role, ["hr", "admin", "owner"]);
}

export function canRunComplianceScan(role: StaffRole) {
  return roleIn(role, ["operations", "hr", "admin", "owner"]);
}

export function canManageTeam(role: StaffRole) {
  return roleIn(role, ["admin", "owner"]);
}
