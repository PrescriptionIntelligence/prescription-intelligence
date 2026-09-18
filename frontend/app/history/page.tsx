"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { authFetch, isAuthenticated } from "@/lib/auth";
import AppShell from "@/components/AppShell";
import { Suspense } from "react";

// =========================================================
// TYPES
// =========================================================

type Medicine = {
  id: string;
  name: string;
  generic_name: string | null;
  extraction_confidence: number | null;
  normalization_confidence: number | null;
};

type SafetyFlag = {
  type: string;
  severity: string;
  message: string;
};

type Prescription = {
  id: string;
  prescription_id: string;
  raw_text: string | null;
  status: string;
  review_status: string;
  safety_flags: SafetyFlag[];
  file_name: string | null;
  created_at: string;
  medicines: Medicine[];
};

const PAGE_SIZE = 20;

// =========================================================
// HELPERS
// =========================================================

function formatDate(value: string): string {
  try {
    return new Date(value).toLocaleString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return value;
  }
}

function getPipelineStatusBadge(status: string) {
  if (status === "analyzed") {
    return {
      label: "Analyzed",
      className: "bg-[#EDF8F1] text-[#35664D] border-[#CBE0D3]",
    };
  }
  if (status === "ocr_failed") {
    return {
      label: "OCR failed",
      className: "bg-[#FFF0F0] text-[#A74646] border-[#E8CECA]",
    };
  }
  if (status === "uploaded") {
    return {
      label: "Uploaded",
      className: "bg-[#F5F8F6] text-[#526158] border-[#DFE6E1]",
    };
  }
  return {
    label: status,
    className: "bg-[#F5F8F6] text-[#526158] border-[#DFE6E1]",
  };
}

function getReviewStatusBadge(reviewStatus: string) {
  switch (reviewStatus) {
    case "verified":
      return {
        label: "Verified",
        className: "bg-[#EDF8F1] text-[#35664D] border-[#CBE0D3]",
      };
    case "rejected":
      return {
        label: "Rejected",
        className: "bg-[#FFF0F0] text-[#A74646] border-[#E8CECA]",
      };
    case "under_review":
      return {
        label: "Under review",
        className: "bg-[#EDF4FB] text-[#1E4B8C] border-[#C8DAF5]",
      };
    case "needs_clarification":
      return {
        label: "Needs clarification",
        className: "bg-[#FFF7DF] text-[#705617] border-[#EBDCAE]",
      };
    case "pending":
    default:
      return {
        label: "Pending review",
        className: "bg-[#FFF7DF] text-[#705617] border-[#EBDCAE]",
      };
  }
}

function getSafetyFlags(prescription: Prescription): SafetyFlag[] {
  return (prescription.safety_flags || []).filter(
    (flag) =>
      flag.type !== "ocr_extraction_failed" &&
      flag.type !== "poor_ocr_quality"
  );
}

function hasHighPriority(prescription: Prescription): boolean {
  return getSafetyFlags(prescription).some((flag) => {
    const s = flag.severity.toLowerCase();
    return s === "high" || s === "error";
  });
}

function averageConfidence(medicines: Medicine[]): number | null {
  const vals: number[] = [];
  for (const m of medicines) {
    const candidates = [m.extraction_confidence, m.normalization_confidence].filter(
      (v): v is number => v !== null && v !== undefined
    );
    if (candidates.length > 0) {
      vals.push(candidates.reduce((s, v) => s + v, 0) / candidates.length);
    }
  }
  if (vals.length === 0) return null;
  return vals.reduce((s, v) => s + v, 0) / vals.length;
}

function getConfidenceLabel(c: number | null): string {
  if (c === null) return "—";
  if (c >= 0.85) return "High";
  if (c >= 0.7) return "Fair";
  return "Low";
}

function getConfidenceClass(c: number | null): string {
  if (c === null) return "text-[#9AA39E]";
  if (c >= 0.85) return "text-[#35664D]";
  if (c >= 0.7) return "text-[#A47B2C]";
  return "text-[#A74646]";
}

// =========================================================
// REVIEW STATUS FILTER OPTIONS
// =========================================================

const REVIEW_STATUS_OPTIONS = [
  { value: "all", label: "All reviews" },
  { value: "pending", label: "Pending review" },
  { value: "under_review", label: "Under review" },
  { value: "needs_clarification", label: "Needs clarification" },
  { value: "verified", label: "Verified" },
  { value: "rejected", label: "Rejected" },
];

const PIPELINE_STATUS_OPTIONS = [
  { value: "all", label: "All" },
  { value: "analyzed", label: "Analyzed" },
  { value: "uploaded", label: "Uploaded" },
  { value: "ocr_failed", label: "OCR failed" },
];

// =========================================================
// INNER COMPONENT (needs useSearchParams)
// =========================================================

function HistoryContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [skip, setSkip] = useState(0);
  const [hasMore, setHasMore] = useState(false);

  // Filters — initialised from URL on mount
  const [search, setSearch] = useState("");
  const [reviewStatusFilter, setReviewStatusFilter] = useState("all");
  const [pipelineStatusFilter, setPipelineStatusFilter] = useState("all");

  // We track whether filters have been initialised from the URL
  const filtersReady = useRef(false);
  // Debounce timer for search
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // -------------------------------------------------------
  // Bootstrap filters from URL params on mount
  // -------------------------------------------------------
  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/sign-in");
      return;
    }

    const rs = searchParams.get("review_status") || "all";
    const ps = searchParams.get("status") || "all";
    const q = searchParams.get("search") || "";

    setReviewStatusFilter(rs);
    setPipelineStatusFilter(ps);
    setSearch(q);
    filtersReady.current = true;

    // Initial load with URL params
    fetchPrescriptions(0, rs, ps, q, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // -------------------------------------------------------
  // Core fetch function (server-side filtering)
  // -------------------------------------------------------
  async function fetchPrescriptions(
    offset: number,
    rs: string,
    ps: string,
    q: string,
    replace: boolean
  ) {
    if (offset === 0) {
      setLoading(true);
    }
    setError("");

    try {
      const params = new URLSearchParams();
      params.set("skip", String(offset));
      params.set("limit", String(PAGE_SIZE));

      if (rs !== "all") params.set("review_status", rs);
      if (ps !== "all") params.set("status", ps);
      if (q.trim()) params.set("search", q.trim());

      const response = await authFetch(`/prescriptions?${params.toString()}`);

      if (!response.ok) {
        throw new Error("Failed to load prescription history.");
      }

      const data = (await response.json()) as Prescription[];

      if (replace) {
        setPrescriptions(data);
      } else {
        setPrescriptions((prev) => [...prev, ...data]);
      }

      setHasMore(data.length === PAGE_SIZE);
      setSkip(offset + data.length);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load prescription history.");
    } finally {
      setLoading(false);
    }
  }

  // -------------------------------------------------------
  // Sync URL whenever filters change (after initial mount)
  // -------------------------------------------------------
  function syncUrl(rs: string, ps: string, q: string) {
    const params = new URLSearchParams();
    if (rs !== "all") params.set("review_status", rs);
    if (ps !== "all") params.set("status", ps);
    if (q.trim()) params.set("search", q.trim());
    const qs = params.toString();
    window.history.replaceState(null, "", qs ? `/history?${qs}` : "/history");
  }

  // -------------------------------------------------------
  // Filter change handlers — reset pagination
  // -------------------------------------------------------
  function handleReviewStatusChange(value: string) {
    setReviewStatusFilter(value);
    setSkip(0);
    syncUrl(value, pipelineStatusFilter, search);
    fetchPrescriptions(0, value, pipelineStatusFilter, search, true);
  }

  function handlePipelineStatusChange(value: string) {
    setPipelineStatusFilter(value);
    setSkip(0);
    syncUrl(reviewStatusFilter, value, search);
    fetchPrescriptions(0, reviewStatusFilter, value, search, true);
  }

  function handleSearchChange(value: string) {
    setSearch(value);
    // Debounce server fetch by 350ms
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      setSkip(0);
      syncUrl(reviewStatusFilter, pipelineStatusFilter, value);
      fetchPrescriptions(0, reviewStatusFilter, pipelineStatusFilter, value, true);
    }, 350);
  }

  function handleClearFilters() {
    setSearch("");
    setReviewStatusFilter("all");
    setPipelineStatusFilter("all");
    setSkip(0);
    window.history.replaceState(null, "", "/history");
    fetchPrescriptions(0, "all", "all", "", true);
  }

  function handleLoadMore() {
    fetchPrescriptions(skip, reviewStatusFilter, pipelineStatusFilter, search, false);
  }

  const filtersActive =
    search.trim() !== "" ||
    reviewStatusFilter !== "all" ||
    pipelineStatusFilter !== "all";

  return (
    <AppShell>
      <div className="mx-auto max-w-7xl px-6 py-10">

        {/* Header */}
        <div className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#77847D]">
              Analysis history
            </div>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em]">
              Prescription history
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[#69766F]">
              Review previous prescription analyses, extracted medicines, and
              safety findings. Filters are applied server-side across all
              records.
            </p>
          </div>
          <Link
            href="/analyze"
            className="inline-flex w-fit rounded-xl bg-[#17211D] px-4 py-2.5 text-xs font-medium text-white transition hover:bg-[#26332D]"
          >
            + New analysis
          </Link>
        </div>

        {/* Error */}
        {error && (
          <div className="mt-6 rounded-xl border border-[#EAD8D2] bg-[#FBF5F2] px-4 py-3 text-xs text-[#8B5547]">
            {error}
          </div>
        )}

        {/* Filters */}
        <div className="mt-8 rounded-2xl border border-[#DFE6E1] bg-white p-4">
          <div className="grid gap-4 md:grid-cols-[1fr_220px_200px_auto] md:items-end">
            {/* Search */}
            <div>
              <label
                htmlFor="history-search"
                className="mb-2 block text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8A948F]"
              >
                Search
              </label>
              <input
                id="history-search"
                type="text"
                value={search}
                onChange={(e) => handleSearchChange(e.target.value)}
                placeholder="Prescription ID or file name"
                className="h-11 w-full rounded-xl border border-[#DFE6E1] bg-[#FAFCFB] px-4 text-sm text-[#17211D] outline-none placeholder:text-[#9AA39E] focus:border-[#9AAEA4] focus:bg-white"
              />
            </div>

            {/* Review status */}
            <div>
              <label
                htmlFor="history-review-status"
                className="mb-2 block text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8A948F]"
              >
                Review status
              </label>
              <select
                id="history-review-status"
                value={reviewStatusFilter}
                onChange={(e) => handleReviewStatusChange(e.target.value)}
                className="h-11 w-full rounded-xl border border-[#DFE6E1] bg-[#FAFCFB] px-4 text-sm text-[#17211D] outline-none focus:border-[#9AAEA4] focus:bg-white"
              >
                {REVIEW_STATUS_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Pipeline status */}
            <div>
              <label
                htmlFor="history-pipeline-status"
                className="mb-2 block text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8A948F]"
              >
                Pipeline
              </label>
              <select
                id="history-pipeline-status"
                value={pipelineStatusFilter}
                onChange={(e) => handlePipelineStatusChange(e.target.value)}
                className="h-11 w-full rounded-xl border border-[#DFE6E1] bg-[#FAFCFB] px-4 text-sm text-[#17211D] outline-none focus:border-[#9AAEA4] focus:bg-white"
              >
                {PIPELINE_STATUS_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Clear */}
            <div className="flex items-end">
              {filtersActive && (
                <button
                  type="button"
                  onClick={handleClearFilters}
                  className="h-11 rounded-xl border border-[#DFE6E1] bg-white px-4 text-xs font-medium text-[#526158] transition hover:bg-[#FAFCFB]"
                >
                  Clear
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Loading skeleton */}
        {loading && prescriptions.length === 0 ? (
          <div className="mt-8 rounded-2xl border border-[#DFE6E1] bg-white px-8 py-16 text-center">
            <p className="text-sm text-[#8A948F]">Loading history…</p>
          </div>
        ) : prescriptions.length === 0 ? (
          <div className="mt-8 rounded-2xl border border-dashed border-[#DFE6E1] bg-white px-8 py-16 text-center">
            <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl border border-[#DFE6E1] bg-[#FAFCFB] text-sm font-semibold text-[#526158]">
              Rx
            </div>
            <h3 className="mt-4 text-sm font-medium text-[#526158]">
              {filtersActive ? "No matching prescriptions" : "No prescriptions yet"}
            </h3>
            <p className="mt-2 text-xs text-[#9AA4A0]">
              {filtersActive
                ? "Try adjusting the filters or clearing the search."
                : "Upload your first prescription to get started."}
            </p>
            {filtersActive ? (
              <button
                type="button"
                onClick={handleClearFilters}
                className="mt-5 text-xs font-medium text-[#526C5D] hover:underline"
              >
                Clear filters
              </button>
            ) : (
              <Link
                href="/analyze"
                className="mt-6 inline-flex rounded-xl bg-[#17211D] px-5 py-2.5 text-xs font-medium text-white transition hover:bg-[#26332D]"
              >
                Analyze prescription
              </Link>
            )}
          </div>
        ) : (
          <>
            <div className="mt-8 overflow-hidden rounded-2xl border border-[#DFE6E1] bg-white">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[900px] text-sm">
                  <thead>
                    <tr className="border-b border-[#E8EDE9] bg-[#FAFCFB] text-[10px] uppercase tracking-[0.12em] text-[#8A948F]">
                      <th className="px-5 py-3.5 text-left font-medium">Prescription</th>
                      <th className="px-5 py-3.5 text-left font-medium">Date</th>
                      <th className="px-5 py-3.5 text-left font-medium">Pipeline</th>
                      <th className="px-5 py-3.5 text-left font-medium">Review status</th>
                      <th className="px-5 py-3.5 text-right font-medium">Medicines</th>
                      <th className="px-5 py-3.5 text-right font-medium">Safety</th>
                      <th className="px-5 py-3.5 text-right font-medium">Confidence</th>
                      <th className="px-5 py-3.5" />
                    </tr>
                  </thead>
                  <tbody>
                    {prescriptions.map((prescription, index) => {
                      const pipeline = getPipelineStatusBadge(prescription.status);
                      const review = getReviewStatusBadge(
                        prescription.review_status || "pending"
                      );
                      const safetyFlags = getSafetyFlags(prescription);
                      const highPriority = hasHighPriority(prescription);
                      const confidence = averageConfidence(prescription.medicines);

                      return (
                        <tr
                          key={prescription.prescription_id}
                          className={
                            index > 0
                              ? "border-t border-[#EDF0EE] hover:bg-[#FAFCFB]"
                              : "hover:bg-[#FAFCFB]"
                          }
                        >
                          <td className="px-5 py-4">
                            <div className="font-mono text-xs font-medium text-[#17211D]">
                              {prescription.prescription_id}
                            </div>
                            <div className="mt-1 max-w-[200px] truncate text-[10px] text-[#8A948F]">
                              {prescription.file_name || "Prescription image"}
                            </div>
                          </td>

                          <td className="px-5 py-4 text-xs text-[#69766F]">
                            {formatDate(prescription.created_at)}
                          </td>

                          {/* Pipeline status */}
                          <td className="px-5 py-4">
                            <span
                              className={`inline-flex rounded-lg border px-2.5 py-1 text-[10px] font-medium ${pipeline.className}`}
                            >
                              {pipeline.label}
                            </span>
                          </td>

                          {/* Review status — distinct column */}
                          <td className="px-5 py-4">
                            <span
                              className={`inline-flex rounded-lg border px-2.5 py-1 text-[10px] font-medium ${review.className}`}
                            >
                              {review.label}
                            </span>
                          </td>

                          <td className="px-5 py-4 text-right">
                            <div className="text-xs font-medium">
                              {prescription.medicines.length}
                            </div>
                            <div className="mt-1 max-w-[160px] truncate text-[10px] text-[#8A948F]">
                              {prescription.medicines.map((m) => m.name).join(", ")}
                            </div>
                          </td>

                          <td className="px-5 py-4 text-right">
                            {safetyFlags.length === 0 ? (
                              <span className="text-xs text-[#9AA39E]">0</span>
                            ) : (
                              <div>
                                <div
                                  className={`text-xs font-semibold ${
                                    highPriority ? "text-[#A74646]" : "text-[#A47B2C]"
                                  }`}
                                >
                                  {safetyFlags.length}
                                </div>
                                <div className="mt-1 text-[10px] text-[#8A948F]">
                                  {highPriority ? "High priority" : "Caution"}
                                </div>
                              </div>
                            )}
                          </td>

                          <td className="px-5 py-4 text-right">
                            <div
                              className={`text-xs font-semibold ${getConfidenceClass(confidence)}`}
                            >
                              {getConfidenceLabel(confidence)}
                            </div>
                            {confidence !== null && (
                              <div className="mt-1 text-[10px] text-[#9AA39E]">
                                {Math.round(confidence * 100)}%
                              </div>
                            )}
                          </td>

                          <td className="px-5 py-4 text-right">
                            <Link
                              href={`/analysis/${prescription.prescription_id}`}
                              className="text-xs font-medium text-[#526C5D] hover:underline"
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

              {hasMore && (
                <div className="border-t border-[#EDF0EE] px-5 py-4 text-center">
                  <button
                    type="button"
                    onClick={handleLoadMore}
                    disabled={loading}
                    className="text-xs font-medium text-[#526C5D] hover:underline disabled:opacity-50"
                  >
                    {loading ? "Loading…" : "Load more"}
                  </button>
                </div>
              )}
            </div>

            {prescriptions.length > 0 && (
              <div className="mt-8 border-t border-[#DFE6E1] pt-5 text-[10px] leading-5 text-[#8A948F]">
                Showing {prescriptions.length} loaded prescription
                {prescriptions.length !== 1 ? "s" : ""}
                {filtersActive ? " (filters applied)" : ""}.
                Prescription Intelligence provides AI-generated decision support
                only. Pharmacist verification is required before dispensing.
              </div>
            )}
          </>
        )}
      </div>
    </AppShell>
  );
}

// =========================================================
// PAGE (Suspense wrapper required for useSearchParams)
// =========================================================

export default function HistoryPage() {
  return (
    <Suspense fallback={
      <div className="flex min-h-screen items-center justify-center bg-[#f4f7f5]">
        <div className="text-sm text-[#718078]">Loading history…</div>
      </div>
    }>
      <HistoryContent />
    </Suspense>
  );
}
