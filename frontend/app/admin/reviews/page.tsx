"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Clock3,
  FileText,
  Filter,
  Loader2,
  RefreshCw,
  Search,
  ShieldAlert,
  XCircle,
} from "lucide-react";

import {
  authFetch,
  fetchMe,
  getUser,
  isAuthenticated,
  logout,
  type User,
} from "../../../lib/auth";

type ReviewStatus =
  | "pending"
  | "under_review"
  | "verified"
  | "needs_clarification"
  | "rejected";

type ReviewItem = {
  id: string;
  prescription_id: string;
  file_name: string | null;
  status: string | null;
  review_status: ReviewStatus;
  organization: {
    id: string;
    name: string;
    slug: string;
  } | null;
  uploaded_by: {
    id: string;
    name: string;
    email: string;
  } | null;
  customer: {
    id: string;
    name: string | null;
  } | null;
  total_findings?: number;
  high_priority_findings?: number;
  reviewed_by_id: string | null;
  reviewed_at: string | null;
  review_notes: string | null;
  raw_text_available: boolean;
};

type ReviewDetail = {
  id: string;
  prescription_id: string;
  file_name: string | null;
  status: string | null;
  review_status: ReviewStatus;
  organization: ReviewItem["organization"];
  uploaded_by: ReviewItem["uploaded_by"];
  customer: ReviewItem["customer"];
  reviewer: {
    id: string;
    name: string;
    email: string;
    role: string;
  } | null;
  reviewed_at: string | null;
  review_notes: string | null;
  raw_text: string | null;
  safety_flags: SafetyFlag[];
  total_findings?: number;
  high_priority_findings?: number;
};

type SafetyFlag = {
  type?: string;
  severity?: string;
  medicine?: string | null;
  message?: string | null;
  details?: string | null;
  recommendation?: string | null;
  interaction?: string | null;
  prescription_strength?: string | null;
  reference_strength?: string | null;
  resolution_reason?: string | null;
};

type Stats = {
  total: number;
  pending: number;
  under_review: number;
  needs_clarification: number;
  verified: number;
  rejected: number;
  high_priority: number;
};

const STATUS_OPTIONS: Array<{
  value: "all" | ReviewStatus;
  label: string;
}> = [
  { value: "all", label: "All statuses" },
  { value: "pending", label: "Pending" },
  { value: "under_review", label: "Under review" },
  {
    value: "needs_clarification",
    label: "Needs clarification",
  },
  { value: "verified", label: "Verified" },
  { value: "rejected", label: "Rejected" },
];

function formatStatus(status: ReviewStatus) {
  switch (status) {
    case "under_review":
      return "Under review";
    case "needs_clarification":
      return "Needs clarification";
    case "verified":
      return "Verified";
    case "rejected":
      return "Rejected";
    default:
      return "Pending";
  }
}

function statusClass(status: ReviewStatus) {
  switch (status) {
    case "verified":
      return "bg-[#EDF8F1] text-[#35664D] border-[#CBE0D3]";
    case "under_review":
      return "bg-[#FFF7DF] text-[#A47B2C] border-[#E8D7A5]";
    case "needs_clarification":
      return "bg-[#FFF7DF] text-[#8B681F] border-[#E8D7A5]";
    case "rejected":
      return "bg-[#FFF0F0] text-[#A74646] border-[#E8CACA]";
    default:
      return "bg-[#F2F5F3] text-[#526158] border-[#DFE6E1]";
  }
}

function severityClass(severity?: string) {
  const value = String(severity || "").toLowerCase();

  if (
    value === "high" ||
    value === "critical" ||
    value === "error"
  ) {
    return "border-[#E7CACA] bg-[#FFF0F0] text-[#A74646]";
  }

  if (value === "medium") {
    return "border-[#E8D7A5] bg-[#FFF7DF] text-[#8B681F]";
  }

  return "border-[#DFE6E1] bg-[#FAFCFB] text-[#526158]";
}

function formatDate(value: string | null) {
  if (!value) return "Not reviewed";

  try {
    return new Date(value).toLocaleString(undefined, {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return value;
  }
}

function getFindingCounts(detail: ReviewDetail) {
  const flags = Array.isArray(detail.safety_flags)
    ? detail.safety_flags
    : [];

  const total = flags.length;

  const highPriority = flags.filter((flag) => {
    const severity = String(
      flag?.severity || ""
    ).toLowerCase();

    return (
      severity === "high" ||
      severity === "critical" ||
      severity === "error"
    );
  }).length;

  return {
    total,
    highPriority,
  };
}

export default function AdminReviewsPage() {
  const [user, setUser] = useState<User | null>(getUser());
  const [loading, setLoading] = useState(true);

  const [items, setItems] = useState<ReviewItem[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);

  const [search, setSearch] = useState("");
  const [status, setStatus] =
    useState<"all" | ReviewStatus>("all");
  const [priorityOnly, setPriorityOnly] =
    useState(false);

  const [selectedId, setSelectedId] =
    useState<string | null>(null);

  const [detail, setDetail] =
    useState<ReviewDetail | null>(null);

  const [detailLoading, setDetailLoading] =
    useState(false);

  const [actionLoading, setActionLoading] =
    useState<string | null>(null);

  const [note, setNote] = useState("");

  const [error, setError] =
    useState<string | null>(null);

  const isAdmin = user?.role === "admin";

  async function loadReviews() {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams();

      if (search.trim()) {
        params.set("q", search.trim());
      }

      if (status !== "all") {
        params.set("review_status", status);
      }

      if (priorityOnly) {
        params.set("priority", "high");
      }

      params.set("skip", "0");
      params.set("limit", "100");

      const [reviewsResponse, statsResponse] =
        await Promise.all([
          authFetch(
            `/admin/reviews?${params.toString()}`
          ),
          authFetch("/admin/reviews/stats"),
        ]);

      if (
        reviewsResponse.status === 401 ||
        reviewsResponse.status === 403
      ) {
        logout();
        return;
      }

      if (!reviewsResponse.ok) {
        throw new Error(
          "Unable to load prescription reviews."
        );
      }

      if (!statsResponse.ok) {
        throw new Error(
          "Unable to load review statistics."
        );
      }

      const reviewsData =
        await reviewsResponse.json();

      const statsData =
        await statsResponse.json();

      setItems(reviewsData.items || []);
      setStats(statsData);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Something went wrong."
      );
    } finally {
      setLoading(false);
    }
  }

  async function loadDetail(
    prescriptionId: string
  ) {
    setSelectedId(prescriptionId);
    setDetailLoading(true);
    setDetail(null);
    setError(null);

    try {
      const response = await authFetch(
        `/admin/reviews/${prescriptionId}`
      );

      if (
        response.status === 401 ||
        response.status === 403
      ) {
        logout();
        return;
      }

      if (!response.ok) {
        throw new Error(
          "Unable to load prescription review."
        );
      }

      const data =
        await response.json();

      setDetail({
        ...data,
        safety_flags: Array.isArray(
          data.safety_flags
        )
          ? data.safety_flags
          : [],
      });

      setNote(data.review_notes || "");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load review."
      );
    } finally {
      setDetailLoading(false);
    }
  }

  async function performAction(
    action:
      | "start_review"
      | "confirm"
      | "correct"
      | "dismiss"
      | "clarify"
      | "complete_review"
  ) {
    if (!detail) return;

    setActionLoading(action);
    setError(null);

    try {
      const response = await authFetch(
        `/admin/reviews/${detail.prescription_id}/action`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            action,
            note: note.trim() || null,
          }),
        }
      );

      if (
        response.status === 401 ||
        response.status === 403
      ) {
        logout();
        return;
      }

      const data =
        await response.json();

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            "Unable to update prescription review."
        );
      }

      await loadReviews();
      await loadDetail(
        detail.prescription_id
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to update review."
      );
    } finally {
      setActionLoading(null);
    }
  }

  useEffect(() => {
    let mounted = true;

    async function initialize() {
      if (!isAuthenticated()) {
        window.location.href = "/sign-in";
        return;
      }

      try {
        const currentUser =
          await fetchMe();

        if (!mounted) return;

        if (!currentUser) {
          window.location.href =
            "/sign-in";
          return;
        }

        setUser(currentUser);

        if (
          currentUser.role !== "admin"
        ) {
          window.location.href =
            currentUser.role === "customer"
              ? "/customer"
              : "/dashboard";

          return;
        }

        await loadReviews();
      } catch {
        if (mounted) {
          window.location.href =
            "/sign-in";
        }
      }
    }

    initialize();

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!isAdmin) return;

    const timer =
      window.setTimeout(() => {
        loadReviews();
      }, 300);

    return () =>
      window.clearTimeout(timer);
  }, [
    search,
    status,
    priorityOnly,
    isAdmin,
  ]);

  const summaryText =
    useMemo(() => {
      if (!stats) {
        return "Review activity across the platform.";
      }

      if (stats.high_priority > 0) {
        return `${stats.high_priority} prescription${
          stats.high_priority === 1
            ? ""
            : "s"
        } require high-priority attention.`;
      }

      return "No high-priority prescriptions are currently flagged.";
    }, [stats]);

  const detailFindingCounts =
    useMemo(() => {
      if (!detail) {
        return {
          total: 0,
          highPriority: 0,
        };
      }

      return getFindingCounts(detail);
    }, [detail]);

  if (!isAdmin && !loading) {
    return null;
  }

  return (
    <main className="min-h-screen bg-[#F4F7F5] text-[#17211D]">
      <div className="mx-auto max-w-[1500px] px-5 py-6 lg:px-8">
        <div className="mb-7 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm text-[#7C8881]">
              <span>Admin</span>
              <ChevronRight size={14} />
              <span>
                Prescription reviews
              </span>
            </div>

            <h1 className="text-3xl font-semibold tracking-[-0.03em]">
              Prescription reviews
            </h1>

            <p className="mt-2 max-w-2xl text-sm leading-6 text-[#66736B]">
              Monitor prescription review
              status, safety findings, and
              pharmacist verification activity
              across the platform.
            </p>
          </div>

          <button
            type="button"
            onClick={loadReviews}
            disabled={loading}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-[#DFE6E1] bg-white px-4 text-sm font-medium text-[#17211D] shadow-sm transition hover:bg-[#FAFCFB] disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw
              size={16}
              className={
                loading
                  ? "animate-spin"
                  : ""
              }
            />
            Refresh
          </button>
        </div>

        {error && (
          <div className="mb-6 flex items-start gap-3 rounded-xl border border-[#E7CACA] bg-[#FFF0F0] p-4 text-sm text-[#A74646]">
            <AlertTriangle
              size={18}
              className="mt-0.5 shrink-0"
            />
            <span>{error}</span>
          </div>
        )}

        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Total prescriptions"
            value={
              stats?.total ?? "—"
            }
            icon={
              <FileText size={18} />
            }
          />

          <StatCard
            label="Pending review"
            value={
              stats?.pending ?? "—"
            }
            icon={
              <Clock3 size={18} />
            }
          />

          <StatCard
            label="Under review"
            value={
              stats?.under_review ?? "—"
            }
            icon={
              <ShieldAlert size={18} />
            }
          />

          <StatCard
            label="High priority"
            value={
              stats?.high_priority ?? "—"
            }
            icon={
              <AlertTriangle size={18} />
            }
            danger={Boolean(
              stats &&
                stats.high_priority > 0
            )}
          />
        </section>

        <div className="mt-4 rounded-xl border border-[#DFE6E1] bg-white px-4 py-3 text-sm text-[#526158]">
          {summaryText}
        </div>

        <section className="mt-6 rounded-2xl border border-[#DFE6E1] bg-white">
          <div className="border-b border-[#DFE6E1] p-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
              <div className="relative min-w-0 flex-1">
                <Search
                  size={17}
                  className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[#9AA39E]"
                />

                <input
                  value={search}
                  onChange={(event) =>
                    setSearch(
                      event.target.value
                    )
                  }
                  placeholder="Search prescription ID or file name"
                  className="h-10 w-full rounded-lg border border-[#DFE6E1] bg-[#FAFCFB] pl-10 pr-3 text-sm outline-none transition placeholder:text-[#9AA39E] focus:border-[#8AA997] focus:bg-white"
                />
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <div className="relative">
                  <Filter
                    size={15}
                    className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[#7C8881]"
                  />

                  <select
                    value={status}
                    onChange={(event) =>
                      setStatus(
                        event.target
                          .value as
                          | "all"
                          | ReviewStatus
                      )
                    }
                    className="h-10 appearance-none rounded-lg border border-[#DFE6E1] bg-white pl-9 pr-8 text-sm text-[#526158] outline-none"
                  >
                    {STATUS_OPTIONS.map(
                      (option) => (
                        <option
                          key={
                            option.value
                          }
                          value={
                            option.value
                          }
                        >
                          {
                            option.label
                          }
                        </option>
                      )
                    )}
                  </select>
                </div>

                <button
                  type="button"
                  onClick={() =>
                    setPriorityOnly(
                      (value) => !value
                    )
                  }
                  className={`h-10 rounded-lg border px-3 text-sm font-medium transition ${
                    priorityOnly
                      ? "border-[#E7CACA] bg-[#FFF0F0] text-[#A74646]"
                      : "border-[#DFE6E1] bg-white text-[#526158] hover:bg-[#FAFCFB]"
                  }`}
                >
                  High priority only
                </button>
              </div>
            </div>
          </div>

          <div className="hidden grid-cols-[1.5fr_1.25fr_1fr_0.7fr_0.8fr_28px] gap-4 border-b border-[#DFE6E1] px-5 py-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#9AA39E] lg:grid">
            <span>Prescription</span>
            <span>Pharmacy</span>
            <span>Review status</span>
            <span>Findings</span>
            <span>Priority</span>
            <span />
          </div>

          {loading ? (
            <div className="flex min-h-[280px] items-center justify-center">
              <div className="flex items-center gap-2 text-sm text-[#7C8881]">
                <Loader2
                  size={18}
                  className="animate-spin"
                />
                Loading review queue...
              </div>
            </div>
          ) : items.length === 0 ? (
            <div className="flex min-h-[280px] flex-col items-center justify-center px-6 text-center">
              <div className="mb-3 rounded-full bg-[#FAFCFB] p-3 text-[#7C8881]">
                <FileText size={22} />
              </div>

              <p className="font-medium text-[#17211D]">
                No prescriptions found
              </p>

              <p className="mt-1 max-w-md text-sm text-[#7C8881]">
                Try changing the search or
                review filters.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-[#DFE6E1]">
              {items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() =>
                    loadDetail(
                      item.prescription_id
                    )
                  }
                  className="group grid w-full gap-4 px-5 py-4 text-left transition hover:bg-[#FAFCFB] lg:grid-cols-[1.5fr_1.25fr_1fr_0.7fr_0.8fr_28px] lg:items-center"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-[#17211D]">
                        {
                          item.prescription_id
                        }
                      </span>

                      {item.file_name && (
                        <span className="hidden truncate text-xs text-[#9AA39E] xl:block">
                          {item.file_name}
                        </span>
                      )}
                    </div>

                    <p className="mt-1 text-xs text-[#7C8881]">
                      {item.uploaded_by
                        ?.name ||
                        "Unknown uploader"}
                    </p>
                  </div>

                  <div>
                    <p className="text-sm font-medium text-[#526158]">
                      {item.organization
                        ?.name ||
                        "Unassigned"}
                    </p>

                    <p className="mt-1 text-xs text-[#9AA39E]">
                      {item.organization
                        ?.slug ||
                        "No organization"}
                    </p>
                  </div>

                  <div>
                    <span
                      className={`inline-flex rounded-md border px-2.5 py-1 text-xs font-medium ${statusClass(
                        item.review_status
                      )}`}
                    >
                      {formatStatus(
                        item.review_status
                      )}
                    </span>
                  </div>

                  <div className="text-sm text-[#526158]">
                    {item.total_findings ??
                      0}

                    <span className="ml-1 text-xs text-[#9AA39E]">
                      total
                    </span>
                  </div>

                  <div>
                    {(item.high_priority_findings ??
                      0) > 0 ? (
                      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#A74646]">
                        <AlertTriangle
                          size={14}
                        />

                        {
                          item.high_priority_findings
                        }
                      </span>
                    ) : (
                      <span className="text-xs text-[#9AA39E]">
                        None
                      </span>
                    )}
                  </div>

                  <ChevronRight
                    size={17}
                    className="text-[#B0B8B3] transition group-hover:translate-x-0.5 group-hover:text-[#526158]"
                  />

                  <div className="lg:hidden">
                    <div className="mt-2 flex flex-wrap gap-2 text-xs text-[#7C8881]">
                      <span>
                        {item.total_findings ??
                          0}{" "}
                        findings
                      </span>

                      {(item.high_priority_findings ??
                        0) > 0 && (
                        <span className="font-medium text-[#A74646]">
                          {
                            item.high_priority_findings
                          }{" "}
                          high priority
                        </span>
                      )}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </section>

        {selectedId && (
          <div className="fixed inset-0 z-50 flex justify-end bg-black/20">
            <button
              type="button"
              aria-label="Close review"
              onClick={() => {
                setSelectedId(null);
                setDetail(null);
              }}
              className="absolute inset-0 cursor-default"
            />

            <aside className="relative z-10 flex h-full w-full max-w-2xl flex-col border-l border-[#DFE6E1] bg-[#F4F7F5] shadow-2xl">
              <div className="flex items-center justify-between border-b border-[#DFE6E1] bg-white px-5 py-4">
                <div>
                  <p className="text-xs font-medium uppercase tracking-[0.12em] text-[#9AA39E]">
                    Prescription review
                  </p>

                  <h2 className="mt-1 text-xl font-semibold tracking-[-0.02em]">
                    {selectedId}
                  </h2>
                </div>

                <button
                  type="button"
                  onClick={() => {
                    setSelectedId(null);
                    setDetail(null);
                  }}
                  className="rounded-lg border border-[#DFE6E1] bg-white p-2 text-[#526158] hover:bg-[#FAFCFB]"
                >
                  <XCircle
                    size={18}
                  />
                </button>
              </div>

              {detailLoading ? (
                <div className="flex flex-1 items-center justify-center">
                  <div className="flex items-center gap-2 text-sm text-[#7C8881]">
                    <Loader2
                      size={18}
                      className="animate-spin"
                    />
                    Loading prescription...
                  </div>
                </div>
              ) : detail ? (
                <div className="flex-1 overflow-y-auto">
                  <div className="space-y-4 p-5">
                    <div className="rounded-xl border border-[#DFE6E1] bg-white p-4">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold">
                            {
                              detail.prescription_id
                            }
                          </p>

                          <p className="mt-1 text-xs text-[#7C8881]">
                            {detail.file_name ||
                              "Prescription source"}
                          </p>
                        </div>

                        <span
                          className={`rounded-md border px-2.5 py-1 text-xs font-medium ${statusClass(
                            detail.review_status
                          )}`}
                        >
                          {formatStatus(
                            detail.review_status
                          )}
                        </span>
                      </div>

                      <div className="mt-4 grid gap-3 sm:grid-cols-2">
                        <InfoItem
                          label="Pharmacy"
                          value={
                            detail
                              .organization
                              ?.name ||
                            "Unassigned"
                          }
                        />

                        <InfoItem
                          label="Uploaded by"
                          value={
                            detail.uploaded_by
                              ?.name ||
                            "Unknown"
                          }
                        />

                        <InfoItem
                          label="Customer"
                          value={
                            detail.customer
                              ?.name ||
                            "Not linked"
                          }
                        />

                        <InfoItem
                          label="Findings"
                          value={`${detailFindingCounts.total} total · ${detailFindingCounts.highPriority} high priority`}
                        />
                      </div>
                    </div>

                    {detailFindingCounts.highPriority >
                      0 && (
                      <div className="rounded-xl border border-[#E7CACA] bg-[#FFF0F0] p-4">
                        <div className="flex items-start gap-3">
                          <ShieldAlert
                            size={19}
                            className="mt-0.5 shrink-0 text-[#A74646]"
                          />

                          <div>
                            <p className="text-sm font-semibold text-[#A74646]">
                              High-priority safety
                              findings
                            </p>

                            <p className="mt-1 text-xs leading-5 text-[#8E5252]">
                              Clinical review is required
                              before this prescription
                              should be considered
                              verified.
                            </p>
                          </div>
                        </div>
                      </div>
                    )}

                    <section className="rounded-xl border border-[#DFE6E1] bg-white">
                      <div className="border-b border-[#DFE6E1] px-4 py-3">
                        <h3 className="text-sm font-semibold">
                          Safety findings
                        </h3>
                      </div>

                      <div className="divide-y divide-[#DFE6E1]">
                        {detail.safety_flags
                          .length === 0 ? (
                          <div className="flex items-center gap-2 p-4 text-sm text-[#35664D]">
                            <CheckCircle2
                              size={17}
                            />
                            No safety findings
                            recorded.
                          </div>
                        ) : (
                          detail.safety_flags.map(
                            (
                              flag,
                              index
                            ) => (
                              <SafetyFinding
                                key={`${flag.type}-${index}`}
                                flag={flag}
                              />
                            )
                          )
                        )}
                      </div>
                    </section>

                    <section className="rounded-xl border border-[#DFE6E1] bg-white p-4">
                      <h3 className="text-sm font-semibold">
                        Review notes
                      </h3>

                      <textarea
                        value={note}
                        onChange={(event) =>
                          setNote(
                            event.target
                              .value
                          )
                        }
                        rows={4}
                        placeholder="Add a reviewer note..."
                        className="mt-3 w-full resize-none rounded-lg border border-[#DFE6E1] bg-[#FAFCFB] p-3 text-sm leading-6 outline-none focus:border-[#8AA997] focus:bg-white"
                      />

                      {detail.reviewer && (
                        <div className="mt-3 text-xs text-[#7C8881]">
                          Last reviewed by{" "}
                          <span className="font-medium text-[#526158]">
                            {
                              detail
                                .reviewer
                                .name
                            }
                          </span>
                          {" · "}
                          {formatDate(
                            detail.reviewed_at
                          )}
                        </div>
                      )}
                    </section>

                    {detail.raw_text && (
                      <details className="rounded-xl border border-[#DFE6E1] bg-white">
                        <summary className="cursor-pointer px-4 py-3 text-sm font-semibold">
                          Source text
                        </summary>

                        <pre className="whitespace-pre-wrap border-t border-[#DFE6E1] p-4 text-xs leading-5 text-[#526158]">
                          {
                            detail.raw_text
                          }
                        </pre>
                      </details>
                    )}
                  </div>
                </div>
              ) : null}

              {detail && (
                <div className="border-t border-[#DFE6E1] bg-white p-4">
                  <div className="mb-3 text-xs text-[#7C8881]">
                    Administrative review action.
                    Every action is recorded in
                    the review audit trail.
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    {detail.review_status ===
                      "pending" && (
                      <ActionButton
                        label="Start review"
                        onClick={() =>
                          performAction(
                            "start_review"
                          )
                        }
                        loading={
                          actionLoading ===
                          "start_review"
                        }
                        primary
                      />
                    )}

                    <ActionButton
                      label="Confirm"
                      onClick={() =>
                        performAction(
                          "confirm"
                        )
                      }
                      loading={
                        actionLoading ===
                        "confirm"
                      }
                      disabled={
                        detail.review_status ===
                        "verified"
                      }
                    />

                    <ActionButton
                      label="Correct"
                      onClick={() =>
                        performAction(
                          "correct"
                        )
                      }
                      loading={
                        actionLoading ===
                        "correct"
                      }
                    />

                    <ActionButton
                      label="Clarification"
                      onClick={() =>
                        performAction(
                          "clarify"
                        )
                      }
                      loading={
                        actionLoading ===
                        "clarify"
                      }
                    />

                    <ActionButton
                      label="Reject"
                      onClick={() =>
                        performAction(
                          "dismiss"
                        )
                      }
                      loading={
                        actionLoading ===
                        "dismiss"
                      }
                      danger
                    />
                  </div>

                  {detailFindingCounts.highPriority >
                    0 && (
                    <p className="mt-3 text-[11px] leading-4 text-[#8E5252]">
                      Confirming a prescription
                      with unresolved high-priority
                      findings keeps it in
                      <strong>
                        {" "}
                        Under review
                      </strong>{" "}
                      rather than marking it
                      verified.
                    </p>
                  )}
                </div>
              )}
            </aside>
          </div>
        )}
      </div>
    </main>
  );
}

function StatCard({
  label,
  value,
  icon,
  danger = false,
}: {
  label: string;
  value: number | string;
  icon: React.ReactNode;
  danger?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-[#DFE6E1] bg-white p-5">
      <div className="flex items-center justify-between">
        <span className="text-sm text-[#7C8881]">
          {label}
        </span>

        <span
          className={
            danger
              ? "text-[#A74646]"
              : "text-[#526158]"
          }
        >
          {icon}
        </span>
      </div>

      <p
        className={`mt-4 text-3xl font-semibold tracking-[-0.03em] ${
          danger
            ? "text-[#A74646]"
            : ""
        }`}
      >
        {value}
      </p>
    </div>
  );
}

function InfoItem({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-lg bg-[#FAFCFB] p-3">
      <p className="text-[11px] font-medium uppercase tracking-[0.1em] text-[#9AA39E]">
        {label}
      </p>

      <p className="mt-1 text-sm font-medium text-[#526158]">
        {value}
      </p>
    </div>
  );
}

function SafetyFinding({
  flag,
}: {
  flag: SafetyFlag;
}) {
  const severity =
    String(
      flag.severity || "low"
    ).toLowerCase();

  const strengthConflict =
    flag.type ===
    "strength_conflict";

  return (
    <div className="p-4">
      <div className="flex items-start gap-3">
        <div
          className={`rounded-lg border p-2 ${severityClass(
            severity
          )}`}
        >
          {severity === "high" ||
          severity === "critical" ||
          severity === "error" ? (
            <AlertTriangle
              size={16}
            />
          ) : (
            <ShieldAlert
              size={16}
            />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-[#17211D]">
              {strengthConflict
                ? "Strength conflict"
                : flag.type ||
                  "Safety finding"}
            </p>

            <span
              className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase ${severityClass(
                severity
              )}`}
            >
              {severity}
            </span>
          </div>

          {flag.medicine && (
            <p className="mt-1 text-xs font-medium text-[#526158]">
              Medicine:{" "}
              {flag.medicine}
            </p>
          )}

          {flag.message && (
            <p className="mt-2 text-sm leading-6 text-[#66736B]">
              {flag.message}
            </p>
          )}

          {strengthConflict && (
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <div className="rounded-lg border border-[#E7CACA] bg-[#FFF0F0] p-3">
                <p className="text-[10px] uppercase tracking-[0.1em] text-[#A74646]">
                  Prescription strength
                </p>

                <p className="mt-1 text-sm font-semibold text-[#A74646]">
                  {flag.prescription_strength ||
                    "Not available"}
                </p>
              </div>

              <div className="rounded-lg border border-[#DFE6E1] bg-[#FAFCFB] p-3">
                <p className="text-[10px] uppercase tracking-[0.1em] text-[#7C8881]">
                  Reference strength
                </p>

                <p className="mt-1 text-sm font-semibold text-[#526158]">
                  {flag.reference_strength ||
                    "Not available"}
                </p>
              </div>
            </div>
          )}

          {flag.recommendation && (
            <p className="mt-2 text-xs leading-5 text-[#526158]">
              <span className="font-semibold">
                Recommended action:
              </span>{" "}
              {flag.recommendation}
            </p>
          )}

          {flag.resolution_reason && (
            <p className="mt-2 text-[11px] text-[#9AA39E]">
              Resolution:{" "}
              {
                flag.resolution_reason
              }
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function ActionButton({
  label,
  onClick,
  loading,
  disabled = false,
  primary = false,
  danger = false,
}: {
  label: string;
  onClick: () => void;
  loading: boolean;
  disabled?: boolean;
  primary?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={
        disabled || loading
      }
      className={`inline-flex h-10 items-center justify-center gap-2 rounded-lg border px-3 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${
        primary
          ? "border-[#35664D] bg-[#35664D] text-white hover:bg-[#2D5842]"
          : danger
          ? "border-[#E7CACA] bg-[#FFF0F0] text-[#A74646] hover:bg-[#FFE7E7]"
          : "border-[#DFE6E1] bg-white text-[#526158] hover:bg-[#FAFCFB]"
      }`}
    >
      {loading && (
        <Loader2
          size={15}
          className="animate-spin"
        />
      )}

      {label}
    </button>
  );
}