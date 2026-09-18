"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  getUser,
  isAuthenticated,
  logout,
  User,
  authFetch,
  getRoleHome,
} from "../../lib/auth";

// =========================================================
// Types
// =========================================================

type RecentPrescription = {
  prescription_id: string;
  file_name: string | null;
  created_at: string;
  status: string;
  medicine_count: number;
  safety_count: number;
  avg_confidence: number | null;
};

type DashboardStats = {
  total_prescriptions: number;
  total_medicines: number;
  prescriptions_with_alerts: number;
  needs_review: number;
  recent_prescriptions: RecentPrescription[];
};

type UsageStatus = {
  plan_tier: string;
  display_name: string;
  monthly_limit: number | null;
  prescriptions_used_this_period: number;
  prescriptions_remaining: number | null;
  review_workflow_enabled: boolean;
  pdf_reports_enabled: boolean;
  at_limit: boolean;
};

// =========================================================
// Helpers
// =========================================================

function formatDate(isoString: string): string {
  try {
    return new Date(isoString).toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return isoString;
  }
}

function confidenceLabel(confidence: number | null): string {
  if (confidence === null || confidence === undefined) return "—";
  if (confidence >= 0.85) return "High";
  if (confidence >= 0.70) return "Fair";
  return "Low";
}

function confidenceColor(confidence: number | null): string {
  if (confidence === null || confidence === undefined) return "text-[#a0aaa5]";
  if (confidence >= 0.85) return "text-[#3a6b4e]";
  if (confidence >= 0.70) return "text-[#756c3a]";
  return "text-[#8b4a3a]";
}

function statusBadge(status: string): { label: string; cls: string } {
  switch (status) {
    case "analyzed":
      return { label: "Analyzed", cls: "bg-[#e8f5ed] text-[#3a6b4e]" };
    case "review_required":
      return { label: "Review required", cls: "bg-[#fff7df] text-[#705617]" };
    case "ocr_failed":
      return { label: "OCR Failed", cls: "bg-[#fef3f2] text-[#8b4a3a]" };
    case "uploaded":
      return { label: "Uploaded", cls: "bg-[#f0f3ff] text-[#3a4a8b]" };
    default:
      return { label: status, cls: "bg-[#f0f0f0] text-[#606060]" };
  }
}

// =========================================================
// Component
// =========================================================

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [statsError, setStatsError] = useState("");
  const [loadingStats, setLoadingStats] = useState(true);
  const [usage, setUsage] = useState<UsageStatus | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/sign-in");
      return;
    }

    const stored = getUser();

    if (!stored) {
      router.replace("/sign-in");
      return;
    }

    // Customers have their own completely separate workspace.
    if (stored.role === "customer") {
      router.replace(getRoleHome(stored));
      return;
    }

    Promise.resolve().then(() => setUser(stored));

    authFetch("/dashboard/stats")
      .then((res) => {
        if (!res.ok) {
          throw new Error("Failed to load dashboard data");
        }

        return res.json();
      })
      .then((data: DashboardStats) => {
        setStats(data);
      })
      .catch((err) => {
        setStatsError(
          err instanceof Error
            ? err.message
            : "Could not load statistics"
        );
      })
      .finally(() => {
        setLoadingStats(false);
      });

    // Fetch plan/usage status — only pharmacists have access.
    if (stored.role === "pharmacist") {
      authFetch("/usage")
        .then((res) => (res.ok ? res.json() : null))
        .then((data: UsageStatus | null) => {
          if (data) setUsage(data);
        })
        .catch(() => {
          // Non-critical — silently ignore
        });
    }
  }, [router]);

  if (!user) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#f3f6f3]">
        <div className="text-sm text-[#718078]">Loading workspace…</div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#f3f6f3] text-[#17211d]">

      {/* ================================================
          HEADER
          ================================================ */}

      <header className="border-b border-[#dfe6e1] bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">

          <Link href="/" className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-[#17211d] text-xs font-semibold text-white">
              Rx
            </span>
            <div>
              <div className="text-sm font-semibold">
                Prescription Intelligence
              </div>
              <div className="text-[9px] uppercase tracking-[0.18em] text-[#82908a]">
                Medication intelligence
              </div>
            </div>
          </Link>

          <nav className="hidden items-center gap-6 md:flex">
            <Link
              href="/dashboard"
              className="text-xs font-medium text-[#17211d]"
            >
              Dashboard
            </Link>
            <Link
              href="/history"
              className="text-xs text-[#637069] hover:text-[#17211d]"
            >
              History
            </Link>
            <Link
              href="/analyze"
              className="text-xs text-[#637069] hover:text-[#17211d]"
            >
              Analyze
            </Link>
          </nav>

          <div className="flex items-center gap-4">
            <div className="hidden text-right sm:block">
              <div className="text-xs font-medium">{user.name}</div>
              <div className="text-[10px] text-[#8a948f]">{user.email}</div>
            </div>
            <button
              onClick={logout}
              className="rounded-xl border border-[#dce3de] bg-white px-4 py-2 text-xs font-medium text-[#53625a] hover:border-[#bbc7bf] transition"
            >
              Log out
            </button>
          </div>
        </div>
      </header>

      {/* ================================================
          HERO
          ================================================ */}

      <section className="mx-auto max-w-7xl px-6 py-12">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#77847d]">
            Your workspace
          </div>
          <h1 className="mt-3 text-4xl font-semibold tracking-[-0.05em]">
            Good to see you, {user.name.split(" ")[0]}.
          </h1>
          <p className="mt-3 max-w-xl text-sm leading-6 text-[#737e78]">
            Review prescriptions, inspect extracted medicine information,
            and keep human verification in the loop.
          </p>
        </div>

        {/* ================================================
            STATS GRID
            ================================================ */}

        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">

          <StatCard
            label="Prescriptions"
            value={loadingStats ? "—" : String(stats?.total_prescriptions ?? 0)}
            description="Total analyzed"
            accent="neutral"
          />

          <StatCard
            label="Medicines"
            value={loadingStats ? "—" : String(stats?.total_medicines ?? 0)}
            description="Extracted entries"
            accent="neutral"
          />

          <StatCard
            label="Safety alerts"
            value={loadingStats ? "—" : String(stats?.prescriptions_with_alerts ?? 0)}
            description="Prescriptions with flags"
            accent="alert"
          />

          <Link
            href="/history"
            className="block"
          >
            <StatCard
              label="Needs review"
              value={loadingStats ? "—" : String(stats?.needs_review ?? 0)}
              description="Prescriptions pending pharmacist review"
              accent="warning"
            />
          </Link>
        </div>

        {statsError && (
          <div className="mt-6 rounded-xl border border-[#ead8d2] bg-[#fbf5f2] px-4 py-3 text-xs text-[#8b5547]">
            {statsError} — statistics may be unavailable while the backend is
            starting.
          </div>
        )}

        {/* ================================================
            USAGE / PLAN WIDGET
            ================================================ */}

        {usage && (
          <div className={`mt-6 rounded-2xl border px-5 py-4 ${
            usage.at_limit
              ? "border-[#f0cccc] bg-[#fff5f5]"
              : "border-[#dfe6e1] bg-white"
          }`}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                  usage.plan_tier === "free"
                    ? "bg-[#f0f4f2] text-[#526158]"
                    : usage.plan_tier === "professional"
                    ? "bg-[#edf8f1] text-[#35664d]"
                    : "bg-[#f0f0f8] text-[#3a3a8a]"
                }`}>
                  {usage.display_name}
                </span>
                <span className="text-xs text-[#77847d]">
                  {usage.monthly_limit === null
                    ? `${usage.prescriptions_used_this_period} prescriptions this month — unlimited plan`
                    : usage.at_limit
                    ? `${usage.prescriptions_used_this_period} / ${usage.monthly_limit} — limit reached`
                    : `${usage.prescriptions_used_this_period} / ${usage.monthly_limit} prescriptions this month`}
                </span>
              </div>
              {usage.monthly_limit !== null && !usage.at_limit && (
                <div className="flex items-center gap-2 text-xs text-[#77847d]">
                  <div className="h-1.5 w-32 overflow-hidden rounded-full bg-[#e8ede9]">
                    <div
                      className="h-full rounded-full bg-[#35664d] transition-all"
                      style={{
                        width: `${Math.min(100, Math.round((usage.prescriptions_used_this_period / usage.monthly_limit) * 100))}%`,
                      }}
                    />
                  </div>
                  <span>{usage.prescriptions_remaining} remaining</span>
                </div>
              )}
              {usage.at_limit && (
                <Link
                  href="/dashboard"
                  className="text-xs font-medium text-[#8b4a3a] hover:underline"
                  title="Contact support to upgrade your plan"
                >
                  Limit reached — contact support →
                </Link>
              )}
            </div>
            {!usage.pdf_reports_enabled && (
              <div className="mt-2 text-[11px] text-[#9aa39e]">
                PDF reports are not available on the {usage.display_name} plan.
              </div>
            )}
          </div>
        )}

        {/* ================================================
            ACTION CARDS
            ================================================ */}

        <div className="mt-10 grid gap-5 md:grid-cols-3">

          <Link
            href="/analyze"
            className="group rounded-3xl border border-[#dfe6e1] bg-white p-7 shadow-sm transition hover:-translate-y-1 hover:shadow-lg"
          >
            <div className="grid h-11 w-11 place-items-center rounded-xl bg-[#edf3ef] text-xl text-[#587163]">
              +
            </div>
            <h2 className="mt-7 text-xl font-semibold">
              New prescription
            </h2>
            <p className="mt-2 text-sm leading-6 text-[#7b8580]">
              Upload a prescription image and run the full AI analysis
              pipeline.
            </p>
            <div className="mt-6 text-xs font-medium text-[#526c5d]">
              Start analysis →
            </div>
          </Link>

          <Link
            href="/history"
            className="group rounded-3xl border border-[#dfe6e1] bg-white p-7 shadow-sm transition hover:-translate-y-1 hover:shadow-lg"
          >
            <div className="grid h-11 w-11 place-items-center rounded-xl bg-[#f0f0f8] text-xl text-[#5a5a8a]">
              ≡
            </div>
            <h2 className="mt-7 text-xl font-semibold">
              Analysis history
            </h2>
            <p className="mt-2 text-sm leading-6 text-[#7b8580]">
              Review all previous prescription analyses, medicines, and
              safety findings.
            </p>
            <div className="mt-6 text-xs font-medium text-[#526c5d]">
              View history →
            </div>
          </Link>

          <div className="rounded-3xl border border-[#dfe6e1] bg-white p-7">
            <div className="flex items-center gap-2 text-sm font-medium">
              <span className="h-2 w-2 rounded-full bg-[#6d8b78]" />
              Human review enabled
            </div>
            <p className="mt-3 text-sm leading-6 text-[#7b8580]">
              AI output is decision-support only. Every prescription
              requires human pharmacist verification before dispensing.
            </p>
            <div className="mt-5 text-xs text-[#a0aaa5]">
              Confidence-aware · Not autonomous
            </div>
          </div>
        </div>

        {/* ================================================
            RECENT PRESCRIPTIONS
            ================================================ */}

        {!loadingStats && stats && stats.recent_prescriptions.length > 0 && (
          <section className="mt-14">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold tracking-[-0.03em]">
                Recent prescriptions
              </h2>
              <Link
                href="/history"
                className="text-xs font-medium text-[#526c5d] hover:underline"
              >
                View all →
              </Link>
            </div>

            <div className="mt-6 overflow-hidden rounded-2xl border border-[#dfe6e1] bg-white">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#e8ede9] bg-[#f7faf8] text-xs uppercase tracking-[0.12em] text-[#8a948f]">
                    <th className="px-5 py-3 text-left font-medium">
                      Prescription ID
                    </th>
                    <th className="hidden px-5 py-3 text-left font-medium md:table-cell">
                      Date
                    </th>
                    <th className="px-5 py-3 text-left font-medium">
                      Status
                    </th>
                    <th className="hidden px-5 py-3 text-right font-medium sm:table-cell">
                      Medicines
                    </th>
                    <th className="hidden px-5 py-3 text-right font-medium lg:table-cell">
                      Safety
                    </th>
                    <th className="hidden px-5 py-3 text-right font-medium lg:table-cell">
                      Confidence
                    </th>
                    <th className="px-5 py-3"></th>
                  </tr>
                </thead>
                <tbody>
                  {stats.recent_prescriptions.map((rx, i) => {
                    const badge = statusBadge(rx.status);
                    return (
                      <tr
                        key={rx.prescription_id}
                        className={`${i !== 0 ? "border-t border-[#edf0ee]" : ""} hover:bg-[#fafcfb] transition`}
                      >
                        <td className="px-5 py-4 font-mono text-xs">
                          {rx.prescription_id}
                        </td>
                        <td className="hidden px-5 py-4 text-xs text-[#77847d] md:table-cell">
                          {formatDate(rx.created_at)}
                        </td>
                        <td className="px-5 py-4">
                          <span
                            className={`inline-flex rounded-full px-2.5 py-0.5 text-[10px] font-medium ${badge.cls}`}
                          >
                            {badge.label}
                          </span>
                        </td>
                        <td className="hidden px-5 py-4 text-right text-xs sm:table-cell">
                          {rx.medicine_count}
                        </td>
                        <td className="hidden px-5 py-4 text-right text-xs lg:table-cell">
                          {rx.safety_count > 0 ? (
                            <span className="font-medium text-[#8b4a3a]">
                              {rx.safety_count}
                            </span>
                          ) : (
                            <span className="text-[#a0aaa5]">0</span>
                          )}
                        </td>
                        <td className={`hidden px-5 py-4 text-right text-xs font-medium lg:table-cell ${confidenceColor(rx.avg_confidence)}`}>
                          {confidenceLabel(rx.avg_confidence)}
                        </td>
                        <td className="px-5 py-4 text-right">
                          <Link
                            href={`/analysis/${rx.prescription_id}`}
                            className="text-xs text-[#526c5d] hover:underline"
                          >
                            Open →
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {!loadingStats && stats && stats.recent_prescriptions.length === 0 && (
          <section className="mt-14">
            {/* First-login onboarding panel */}
            <div className="rounded-2xl border border-[#dfe6e1] bg-white overflow-hidden">
              <div className="border-b border-[#edf0ee] bg-[#f7faf8] px-8 py-5">
                <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#77847d]">
                  Get started
                </div>
                <h3 className="mt-1.5 text-lg font-semibold tracking-[-0.03em]">
                  Welcome to your pharmacy workspace
                </h3>
              </div>

              <div className="px-8 py-8">
                <div className="grid gap-5 md:grid-cols-3">

                  <Link
                    href="/analyze"
                    className="group flex flex-col rounded-2xl border border-[#dfe6e1] p-5 transition hover:border-[#b8cfc0] hover:bg-[#f7faf8]"
                  >
                    <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#edf8f1] text-[#35664d]">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
                        <path d="M12 5v14M5 12h14" />
                      </svg>
                    </div>
                    <div className="mt-4">
                      <div className="text-sm font-semibold">Analyze your first prescription</div>
                      <p className="mt-1.5 text-xs leading-5 text-[#7b8580]">
                        Upload a prescription image to run the full AI analysis pipeline.
                      </p>
                    </div>
                    <div className="mt-4 text-xs font-medium text-[#35664d] group-hover:underline">
                      Upload image →
                    </div>
                  </Link>

                  <Link
                    href="/customers"
                    className="group flex flex-col rounded-2xl border border-[#dfe6e1] p-5 transition hover:border-[#b8cfc0] hover:bg-[#f7faf8]"
                  >
                    <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#f4f7f5] text-[#526158]">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
                        <circle cx="12" cy="8" r="3.5" />
                        <path d="M5 21c.8-4.1 3.1-6.2 7-6.2s6.2 2.1 7 6.2" />
                      </svg>
                    </div>
                    <div className="mt-4">
                      <div className="text-sm font-semibold">Add your first customer</div>
                      <p className="mt-1.5 text-xs leading-5 text-[#7b8580]">
                        Register a customer profile to link prescriptions to patients.
                      </p>
                    </div>
                    <div className="mt-4 text-xs font-medium text-[#35664d] group-hover:underline">
                      Add customer →
                    </div>
                  </Link>

                  <Link
                    href="/settings/organization"
                    className="group flex flex-col rounded-2xl border border-[#dfe6e1] p-5 transition hover:border-[#b8cfc0] hover:bg-[#f7faf8]"
                  >
                    <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#f4f7f5] text-[#526158]">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
                        <path d="M4 21h16" />
                        <path d="M6 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16" />
                        <path d="M9 7h6" />
                        <path d="M9 11h2" />
                      </svg>
                    </div>
                    <div className="mt-4">
                      <div className="text-sm font-semibold">Complete your pharmacy profile</div>
                      <p className="mt-1.5 text-xs leading-5 text-[#7b8580]">
                        Add your pharmacy&apos;s contact details, address, and information.
                      </p>
                    </div>
                    <div className="mt-4 text-xs font-medium text-[#35664d] group-hover:underline">
                      Update profile →
                    </div>
                  </Link>

                </div>
              </div>
            </div>
          </section>
        )}
      </section>
    </main>
  );
}

// =========================================================
// Stat card sub-component
// =========================================================

function StatCard({
  label,
  value,
  description,
  accent,
}: {
  label: string;
  value: string;
  description: string;
  accent: "neutral" | "alert" | "warning";
}) {
  const valueColor =
    accent === "alert"
      ? "text-[#8b4a3a]"
      : accent === "warning"
      ? "text-[#756c3a]"
      : "text-[#17211d]";

  return (
    <div className="rounded-2xl border border-[#dfe6e1] bg-white p-6">
      <div className="text-[10px] font-semibold uppercase tracking-[0.15em] text-[#89938e]">
        {label}
      </div>
      <div className={`mt-4 text-4xl font-semibold tracking-[-0.04em] ${valueColor}`}>
        {value}
      </div>
      <div className="mt-1.5 text-xs text-[#8a948f]">{description}</div>
    </div>
  );
}
