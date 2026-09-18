"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  ArrowRight,
  Building2,
  ClipboardCheck,
  FileText,
  ShieldCheck,
  Users,
} from "lucide-react";

import {
  fetchMe,
  getUser,
  isAuthenticated,
  User,
} from "../../lib/auth";
import AppShell from "../../components/AppShell";

type StatCardProps = {
  label: string;
  value: string;
  description: string;
  icon: React.ReactNode;
};

function StatCard({
  label,
  value,
  description,
  icon,
}: StatCardProps) {
  return (
    <div className="rounded-2xl border border-[#DFE6E1] bg-white p-5 shadow-[0_2px_10px_rgba(23,33,29,0.03)]">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-[#7C8881]">{label}</p>
          <p className="mt-2 text-3xl font-semibold tracking-tight text-[#17211D]">
            {value}
          </p>
          <p className="mt-1 text-sm text-[#7C8881]">{description}</p>
        </div>

        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#F4F7F5] text-[#35664D]">
          {icon}
        </div>
      </div>
    </div>
  );
}

type AdminActionProps = {
  title: string;
  description: string;
  href: string;
  icon: React.ReactNode;
};

function AdminAction({
  title,
  description,
  href,
  icon,
}: AdminActionProps) {
  const router = useRouter();

  return (
    <button
      type="button"
      onClick={() => router.push(href)}
      className="group flex w-full items-center justify-between rounded-2xl border border-[#DFE6E1] bg-white p-5 text-left transition hover:border-[#CBE0D3] hover:shadow-[0_4px_18px_rgba(23,33,29,0.05)]"
    >
      <div className="flex items-center gap-4">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[#EDF8F1] text-[#35664D]">
          {icon}
        </div>

        <div>
          <p className="font-semibold text-[#17211D]">{title}</p>
          <p className="mt-1 text-sm text-[#7C8881]">{description}</p>
        </div>
      </div>

      <ArrowRight
        size={18}
        className="text-[#9AA39E] transition group-hover:translate-x-1 group-hover:text-[#35664D]"
      />
    </button>
  );
}

type AdminStats = {
  total_users: number;
  total_organizations: number;
  total_prescriptions: number;
  pending_reviews: number;
  under_review: number;
};

export default function AdminPage() {
  const router = useRouter();

  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState("");

  useEffect(() => {
    async function loadAdmin() {
      if (!isAuthenticated()) {
        router.replace("/sign-in");
        return;
      }

      try {
        const currentUser = await fetchMe();

        if (!currentUser || currentUser.role !== "admin") {
          router.replace("/dashboard");
          return;
        }

        setUser(currentUser);
      } catch {
        const cachedUser = getUser();

        if (!cachedUser || cachedUser.role !== "admin") {
          router.replace("/sign-in");
          return;
        }

        setUser(cachedUser);
      } finally {
        setLoading(false);
      }
    }

    loadAdmin();
  }, [router]);

  // Fetch platform stats once user is confirmed admin
  useEffect(() => {
    if (!user || user.role !== "admin") return;

    setStatsLoading(true);
    import("../../lib/auth").then(({ authFetch }) => {
      authFetch("/admin/stats")
        .then((res) => {
          if (!res.ok) throw new Error("Failed to load stats");
          return res.json();
        })
        .then((data: AdminStats) => setStats(data))
        .catch(() => setStatsError("Statistics unavailable"))
        .finally(() => setStatsLoading(false));
    });
  }, [user]);

  if (loading) {
    return (
      <AppShell>
        <main className="min-h-screen bg-[#F4F7F5] px-6 py-8">
          <div className="mx-auto max-w-7xl">
            <div className="h-8 w-56 animate-pulse rounded-lg bg-[#DFE6E1]" />
            <div className="mt-3 h-4 w-80 animate-pulse rounded bg-[#DFE6E1]" />

            <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {[1, 2, 3, 4].map((item) => (
                <div
                  key={item}
                  className="h-36 animate-pulse rounded-2xl bg-white"
                />
              ))}
            </div>
          </div>
        </main>
      </AppShell>
    );
  }

  if (!user) {
    return null;
  }

  const statValue = (val: number | undefined) =>
    statsLoading ? "—" : val !== undefined ? String(val) : "—";

  return (
    <AppShell>
      <main className="min-h-screen bg-[#F4F7F5]">
      <div className="mx-auto max-w-7xl px-6 py-8 lg:px-8">
        {/* Header */}
        <div className="flex flex-col gap-5 border-b border-[#DFE6E1] pb-7 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="mb-3 flex items-center gap-2 text-sm text-[#7C8881]">
              <ShieldCheck size={16} />
              <span>Administration</span>
            </div>

            <h1 className="text-3xl font-semibold tracking-tight text-[#17211D]">
              Admin overview
            </h1>

            <p className="mt-2 max-w-2xl text-sm leading-6 text-[#526158]">
              Monitor platform activity, pharmacy organizations, customer
              accounts, and prescription review operations from one workspace.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="rounded-xl border border-[#CBE0D3] bg-[#EDF8F1] px-3 py-2 text-sm font-medium text-[#35664D]">
              Administrator
            </div>
          </div>
        </div>

        {/* Platform snapshot */}
        <section className="mt-8">
          <div className="mb-4">
            <h2 className="text-base font-semibold text-[#17211D]">
              Platform snapshot
            </h2>
            <p className="mt-1 text-sm text-[#7C8881]">
              A high-level view of the prescription intelligence platform.
            </p>
          </div>

          {statsError && (
            <div className="mb-4 rounded-xl border border-[#EAD8D2] bg-[#FBF5F2] px-4 py-3 text-xs text-[#8B5547]">
              {statsError}
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Users"
              value={statValue(stats?.total_users)}
              description="Registered platform users"
              icon={<Users size={20} />}
            />

            <StatCard
              label="Pharmacies"
              value={statValue(stats?.total_organizations)}
              description="Connected organizations"
              icon={<Building2 size={20} />}
            />

            <StatCard
              label="Prescriptions"
              value={statValue(stats?.total_prescriptions)}
              description="Analyses processed"
              icon={<FileText size={20} />}
            />

            <StatCard
              label="Pending reviews"
              value={statValue(stats?.pending_reviews)}
              description="Prescriptions awaiting pharmacist review"
              icon={<ClipboardCheck size={20} />}
            />
          </div>
        </section>

        {/* Admin workspace */}
        <section className="mt-10">
          <div className="mb-4">
            <h2 className="text-base font-semibold text-[#17211D]">
              Administration
            </h2>
            <p className="mt-1 text-sm text-[#7C8881]">
              Manage platform entities and review operational activity.
            </p>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <AdminAction
              title="Users"
              description="Review registered accounts and their roles."
              href="/admin/users"
              icon={<Users size={20} />}
            />

            <AdminAction
              title="Pharmacies"
              description="Review pharmacy organizations and memberships."
              href="/admin/pharmacies"
              icon={<Building2 size={20} />}
            />

            <AdminAction
              title="Prescription reviews"
              description="Monitor prescriptions requiring pharmacist review."
              href="/admin/reviews"
              icon={<ClipboardCheck size={20} />}
            />

            <AdminAction
              title="Audit log"
              description="Inspect important review and administrative events."
              href="/admin/audit"
              icon={<Activity size={20} />}
            />
          </div>
        </section>

        {/* Trust / security panel */}
        <section className="mt-10 rounded-2xl border border-[#CBE0D3] bg-[#EDF8F1] p-5">
          <div className="flex items-start gap-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white text-[#35664D]">
              <ShieldCheck size={20} />
            </div>

            <div>
              <h2 className="font-semibold text-[#17211D]">
                Administrative controls
              </h2>

              <p className="mt-1 max-w-3xl text-sm leading-6 text-[#526158]">
                Administrative access is separated from pharmacist and
                customer workspaces. Prescription analysis and clinical
                decisions remain within the appropriate role-specific
                workflows.
              </p>
            </div>
          </div>
        </section>
      </div>
      </main>
    </AppShell>
  );
}