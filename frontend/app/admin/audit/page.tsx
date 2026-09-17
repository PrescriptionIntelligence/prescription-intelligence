"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { authFetch, getUser, isAuthenticated } from "../../../lib/auth";

// =========================================================
// Types
// =========================================================

type ReviewItem = {
  id: string;
  prescription_id: string;
  status: string;
  review_status: string;
  file_name: string | null;
  organization: { id: string; name: string; slug: string } | null;
  customer: { id: string; name: string; customer_code: string } | null;
  uploaded_by: { id: string; name: string; email: string } | null;
  reviewed_by: { id: string; name: string; email: string; role: string } | null;
  reviewed_at: string | null;
  review_notes: string | null;
  findings: {
    total: number;
    critical: number;
    high: number;
    medium: number;
    low: number;
  };
};

type ReviewsResponse = {
  items: ReviewItem[];
  total: number;
  skip: number;
  limit: number;
};

// =========================================================
// Helpers
// =========================================================

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function reviewStatusBadge(status: string): { label: string; cls: string } {
  switch (status) {
    case "verified":
      return { label: "Verified", cls: "bg-[#edf8f1] text-[#35664d] border-[#cbe0d3]" };
    case "rejected":
      return { label: "Rejected", cls: "bg-[#fff0f0] text-[#7b2929] border-[#eccaca]" };
    case "under_review":
      return { label: "Under review", cls: "bg-[#edf4fb] text-[#1e4b8c] border-[#c8daf5]" };
    case "needs_clarification":
      return { label: "Needs clarification", cls: "bg-[#fff7df] text-[#705617] border-[#ebdcae]" };
    default:
      return { label: "Pending", cls: "bg-[#f3f6f4] text-[#526158] border-[#dfe6e1]" };
  }
}

function findingsSummary(findings: ReviewItem["findings"]): string {
  const parts: string[] = [];
  if (findings.critical > 0) parts.push(`${findings.critical} critical`);
  if (findings.high > 0) parts.push(`${findings.high} high`);
  if (findings.medium > 0) parts.push(`${findings.medium} medium`);
  if (findings.low > 0) parts.push(`${findings.low} low`);
  return parts.length > 0 ? parts.join(", ") : "None";
}

// =========================================================
// Component
// =========================================================

export default function AdminAuditPage() {
  const router = useRouter();

  const [items, setItems] = useState<ReviewItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [skip, setSkip] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");

  const LIMIT = 25;

  async function loadPage(offset: number, filter: string, replace: boolean) {
    const busy = offset === 0 ? setLoading : setLoadingMore;
    busy(true);

    try {
      const params = new URLSearchParams({
        skip: String(offset),
        limit: String(LIMIT),
      });
      if (filter) params.set("review_status", filter);

      const response = await authFetch(`/admin/reviews?${params.toString()}`);

      if (!response.ok) {
        throw new Error("Failed to load review records.");
      }

      const data: ReviewsResponse = await response.json();

      if (replace) {
        setItems(data.items);
      } else {
        setItems((prev) => [...prev, ...data.items]);
      }

      setTotal(data.total);
      setHasMore(offset + data.items.length < data.total);
      setSkip(offset + data.items.length);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load records.");
    } finally {
      busy(false);
    }
  }

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/sign-in");
      return;
    }
    const stored = getUser();
    if (!stored || stored.role !== "admin") {
      router.replace("/sign-in");
      return;
    }

    loadPage(0, statusFilter, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  function handleFilterChange(value: string) {
    setStatusFilter(value);
    loadPage(0, value, true);
  }

  function handleLoadMore() {
    loadPage(skip, statusFilter, false);
  }

  return (
    <main className="min-h-screen bg-[#f4f7f5] text-[#17211d]">
      <header className="border-b border-[#dfe6e1] bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <Link href="/admin" className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-[#17211d] text-xs font-semibold text-white">
              Rx
            </span>
            <div>
              <div className="text-sm font-semibold">
                Prescription Intelligence
              </div>
              <div className="text-[9px] uppercase tracking-[0.18em] text-[#82908a]">
                Administrator workspace
              </div>
            </div>
          </Link>
          <nav className="hidden items-center gap-6 md:flex">
            <Link href="/admin" className="text-xs text-[#637069] hover:text-[#17211d]">Overview</Link>
            <Link href="/admin/users" className="text-xs text-[#637069] hover:text-[#17211d]">Users</Link>
            <Link href="/admin/pharmacies" className="text-xs text-[#637069] hover:text-[#17211d]">Pharmacies</Link>
            <Link href="/admin/reviews" className="text-xs text-[#637069] hover:text-[#17211d]">Reviews</Link>
            <Link href="/admin/audit" className="text-xs font-medium text-[#17211d]">Audit log</Link>
          </nav>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-6 py-10">
        {/* Page header */}
        <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#77847d]">
              Administrator
            </div>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em]">
              Prescription review audit log
            </h1>
            <p className="mt-2 text-sm text-[#7b8580]">
              All prescription review records across all pharmacy organizations.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-[#68766f]">
              Status:
            </label>
            <select
              value={statusFilter}
              onChange={(e) => handleFilterChange(e.target.value)}
              className="rounded-xl border border-[#d9e1dc] bg-white px-3 py-2 text-xs outline-none focus:border-[#82988b] focus:ring-2 focus:ring-[#e5ece7]"
            >
              <option value="">All statuses</option>
              <option value="pending">Pending</option>
              <option value="under_review">Under review</option>
              <option value="verified">Verified</option>
              <option value="needs_clarification">Needs clarification</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>
        </div>

        {/* Summary */}
        {!loading && (
          <p className="mb-5 text-xs text-[#7b8580]">
            {total} prescription{total !== 1 ? "s" : ""} total
          </p>
        )}

        {/* Error */}
        {error && (
          <div className="mb-6 rounded-xl border border-[#ead8d2] bg-[#fbf5f2] px-4 py-3 text-xs text-[#8b5547]">
            {error}
          </div>
        )}

        {/* Loading */}
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-[#68766f]">
            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-[#cfd8d3] border-t-[#17211d]" />
            Loading audit records…
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-[#dfe6e1] bg-white px-8 py-12 text-center">
            <p className="text-sm font-medium text-[#526158]">No records found</p>
            <p className="mt-1 text-xs text-[#89938e]">
              {statusFilter ? "Try changing the status filter." : "No prescription review records exist yet."}
            </p>
          </div>
        ) : (
          <>
            <div className="overflow-hidden rounded-2xl border border-[#dfe6e1] bg-white shadow-[0_5px_25px_rgba(28,46,36,0.04)]">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#e8ede9] bg-[#f7faf8] text-xs uppercase tracking-[0.1em] text-[#8a948f]">
                    <th className="px-5 py-3 text-left font-medium">Prescription</th>
                    <th className="hidden px-5 py-3 text-left font-medium md:table-cell">Pharmacy</th>
                    <th className="hidden px-5 py-3 text-left font-medium lg:table-cell">Customer</th>
                    <th className="px-5 py-3 text-left font-medium">Review status</th>
                    <th className="hidden px-5 py-3 text-left font-medium xl:table-cell">Findings</th>
                    <th className="hidden px-5 py-3 text-left font-medium lg:table-cell">Reviewed by</th>
                    <th className="hidden px-5 py-3 text-left font-medium md:table-cell">Date</th>
                    <th className="px-5 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {items.map((item, i) => {
                    const badge = reviewStatusBadge(item.review_status);
                    return (
                      <tr
                        key={item.id}
                        className={`${
                          i !== 0 ? "border-t border-[#edf0ee]" : ""
                        } transition hover:bg-[#fafcfb]`}
                      >
                        <td className="px-5 py-4">
                          <div className="font-mono text-xs text-[#4d5b53]">
                            {item.prescription_id}
                          </div>
                          {item.file_name && (
                            <div className="mt-0.5 max-w-[160px] truncate text-[10px] text-[#89938e]">
                              {item.file_name}
                            </div>
                          )}
                        </td>
                        <td className="hidden px-5 py-4 md:table-cell">
                          <span className="text-xs text-[#526158]">
                            {item.organization?.name ?? "—"}
                          </span>
                        </td>
                        <td className="hidden px-5 py-4 lg:table-cell">
                          {item.customer ? (
                            <div>
                              <div className="text-xs text-[#526158]">
                                {item.customer.name}
                              </div>
                              <div className="font-mono text-[10px] text-[#89938e]">
                                {item.customer.customer_code}
                              </div>
                            </div>
                          ) : (
                            <span className="text-xs text-[#9aa39e]">—</span>
                          )}
                        </td>
                        <td className="px-5 py-4">
                          <span
                            className={`inline-flex rounded-full border px-2.5 py-0.5 text-[10px] font-medium ${badge.cls}`}
                          >
                            {badge.label}
                          </span>
                        </td>
                        <td className="hidden px-5 py-4 xl:table-cell">
                          <span
                            className={`text-xs ${
                              item.findings.high > 0 || item.findings.critical > 0
                                ? "font-medium text-[#8b4a3a]"
                                : "text-[#89938e]"
                            }`}
                          >
                            {findingsSummary(item.findings)}
                          </span>
                        </td>
                        <td className="hidden px-5 py-4 lg:table-cell">
                          {item.reviewed_by ? (
                            <div>
                              <div className="text-xs text-[#526158]">
                                {item.reviewed_by.name}
                              </div>
                              <div className="text-[10px] text-[#89938e]">
                                {item.reviewed_by.role}
                              </div>
                            </div>
                          ) : (
                            <span className="text-xs text-[#9aa39e]">—</span>
                          )}
                        </td>
                        <td className="hidden px-5 py-4 text-xs text-[#89938e] md:table-cell">
                          {item.reviewed_at
                            ? formatDateTime(item.reviewed_at)
                            : "—"}
                        </td>
                        <td className="px-5 py-4 text-right">
                          <Link
                            href={`/admin/reviews?id=${item.prescription_id}`}
                            className="text-xs text-[#526c5d] hover:underline"
                          >
                            View →
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {hasMore && (
              <div className="mt-6 flex justify-center">
                <button
                  onClick={handleLoadMore}
                  disabled={loadingMore}
                  className="rounded-xl border border-[#dfe6e1] bg-white px-5 py-2.5 text-xs font-medium text-[#526158] transition hover:bg-[#f7faf8] disabled:opacity-60"
                >
                  {loadingMore ? "Loading…" : "Load more"}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}
