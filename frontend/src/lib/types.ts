export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export type Me = {
  id: string;
  name: string;
  phone: string;
  email: string;
  role: string;
  payroll_profile_id?: string | null;
  company: { id: string; name: string; slug: string };
};

export type Worker = {
  id: string;
  worker_code: string;
  full_name: string;
  phone: string;
  job_title: string;
  status: string;
  wage_type: string;
  basic_wage: string;
  payroll_ready: boolean;
  default_site: string | null;
};

export type Roster = {
  id: string;
  worker: string;
  site: string;
  shift: string;
  date: string;
  status: string;
};

export type Attendance = {
  id: string;
  worker: string;
  worker_name: string;
  worker_code: string;
  site_name: string;
  work_date: string;
  check_in_at: string;
  check_out_at: string | null;
  status: string;
  outcome: string;
  payable_fraction: string;
  flags: string[];
};
