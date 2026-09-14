"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  ArrowLeft,
  Building2,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Search,
  ShieldCheck,
  Users,
} from "lucide-react";

import {
  authFetch,
  fetchMe,
  getUser,
  isAuthenticated,
  User,
} from "../../../lib/auth";

type PharmacyRow = {
  id: string;
  name: string;
  slug: string;
  phone: string | null;
  email: string | null;
  address: string | null;
  is_active: boolean;
  pharmacist_count: number;
  customer_count: number;
  prescription_count: number;
  created_at: string | null;
};

type PharmaciesResponse = {
  items: PharmacyRow[];
  total: number;
  skip: number;
  limit: number;
};

type PharmacyStats = {
  total_pharmacies: number;
  active_pharmacies: number;
  inactive_pharmacies: number;
};

function formatDate(value: string | null) {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "—";
  }

  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

function statusStyle(isActive: boolean) {
  if (isActive) {
    return "border-[#CBE0D3] bg-[#EDF8F1] text-[#35664D]";
  }

  return "border-[#DFE6E1] bg-[#F4F7F5] text-[#7C8881]";
}

export default function AdminPharmaciesPage() {
  const router = useRouter();

  const [user, setUser] = useState<User | null>(null);

  const [loading, setLoading] = useState(true);
  const [loadingPharmacies, setLoadingPharmacies] =
    useState(true);
  const [loadingStats, setLoadingStats] = useState(true);

  const [pharmacies, setPharmacies] = useState<PharmacyRow[]>(
    []
  );

  const [stats, setStats] = useState<PharmacyStats | null>(
    null
  );

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<
    "all" | "active" | "inactive"
  >("all");

  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);

  const [error, setError] = useState("");

  const pageSize = 20;

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

  async function loadStats() {
    setLoadingStats(true);

    try {
      const response = await authFetch(
        "/admin/pharmacies/stats"
      );

      if (!response.ok) {
        throw new Error(
          "Unable to load pharmacy statistics."
        );
      }

      const data: PharmacyStats = await response.json();

      setStats(data);
    } catch {
      setStats(null);
    } finally {
      setLoadingStats(false);
    }
  }

  async function loadPharmacies() {
    setLoadingPharmacies(true);
    setError("");

    try {
      const params = new URLSearchParams();

      const trimmedSearch = search.trim();

      if (trimmedSearch) {
        params.set("q", trimmedSearch);
      }

      if (statusFilter !== "all") {
        params.set(
          "active",
          statusFilter === "active" ? "true" : "false"
        );
      }

      params.set("skip", String(page * pageSize));
      params.set("limit", String(pageSize));

      const response = await authFetch(
        `/admin/pharmacies?${params.toString()}`
      );

      if (!response.ok) {
        if (response.status === 403) {
          router.replace("/dashboard");
          return;
        }

        throw new Error(
          "Unable to load pharmacies."
        );
      }

      const data: PharmaciesResponse =
        await response.json();

      setPharmacies(data.items ?? []);
      setTotal(data.total ?? 0);
    } catch {
      setPharmacies([]);
      setTotal(0);
      setError(
        "We couldn't load the platform pharmacies. Please try again."
      );
    } finally {
      setLoadingPharmacies(false);
    }
  }

  useEffect(() => {
    if (!user || user.role !== "admin") {
      return;
    }

    loadStats();
  }, [user]);

  useEffect(() => {
    if (!user || user.role !== "admin") {
      return;
    }

    const timeout = window.setTimeout(() => {
      loadPharmacies();
    }, 250);

    return () => {
      window.clearTimeout(timeout);
    };
  }, [user, search, statusFilter, page]);

  function handleSearchChange(value: string) {
    setSearch(value);
    setPage(0);
  }

  function handleStatusChange(
    value: "all" | "active" | "inactive"
  ) {
    setStatusFilter(value);
    setPage(0);
  }

  function refreshData() {
    loadStats();
    loadPharmacies();
  }

  const totalPages = Math.max(
    1,
    Math.ceil(total / pageSize)
  );

  const hasPreviousPage = page > 0;
  const hasNextPage = page + 1 < totalPages;

  if (loading) {
    return (
      <main className="min-h-screen bg-[#F4F7F5] px-6 py-8">
        <div className="mx-auto max-w-7xl">
          <div className="h-5 w-32 animate-pulse rounded bg-[#DFE6E1]" />

          <div className="mt-4 h-9 w-72 animate-pulse rounded-lg bg-[#DFE6E1]" />

          <div className="mt-8 grid gap-4 md:grid-cols-3">
            <div className="h-28 animate-pulse rounded-2xl bg-white" />
            <div className="h-28 animate-pulse rounded-2xl bg-white" />
            <div className="h-28 animate-pulse rounded-2xl bg-white" />
          </div>

          <div className="mt-8 h-20 animate-pulse rounded-2xl bg-white" />

          <div className="mt-4 h-96 animate-pulse rounded-2xl bg-white" />
        </div>
      </main>
    );
  }

  if (!user) {
    return null;
  }

  return (
    <main className="min-h-screen bg-[#F4F7F5]">
      <div className="mx-auto max-w-7xl px-6 py-8 lg:px-8">
        {/* HEADER */}

        <div className="flex flex-col gap-5 border-b border-[#DFE6E1] pb-7 md:flex-row md:items-end md:justify-between">
          <div>
            <button
              type="button"
              onClick={() => router.push("/admin")}
              className="mb-4 inline-flex items-center gap-2 text-sm font-medium text-[#7C8881] transition hover:text-[#35664D]"
            >
              <ArrowLeft size={16} />
              Admin overview
            </button>

            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#EDF8F1] text-[#35664D]">
                <Building2 size={21} />
              </div>

              <div>
                <h1 className="text-3xl font-semibold tracking-tight text-[#17211D]">
                  Pharmacies
                </h1>

                <p className="mt-1 text-sm text-[#7C8881]">
                  Monitor registered pharmacy organizations
                  across the platform.
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={refreshData}
              disabled={
                loadingPharmacies || loadingStats
              }
              className="inline-flex items-center gap-2 rounded-xl border border-[#DFE6E1] bg-white px-3 py-2 text-sm font-medium text-[#526158] transition hover:border-[#CBE0D3] hover:text-[#35664D] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <RefreshCw
                size={15}
                className={
                  loadingPharmacies || loadingStats
                    ? "animate-spin"
                    : ""
                }
              />
              Refresh
            </button>

            <div className="inline-flex items-center gap-2 rounded-xl border border-[#CBE0D3] bg-[#EDF8F1] px-3 py-2 text-sm font-medium text-[#35664D]">
              <ShieldCheck size={16} />
              Admin access
            </div>
          </div>
        </div>

        {/* STATS */}

        <section className="mt-8 grid gap-4 md:grid-cols-3">
          <div className="rounded-2xl border border-[#DFE6E1] bg-white p-5">
            <div className="flex items-center justify-between">
              <p className="text-sm text-[#7C8881]">
                Total pharmacies
              </p>

              <Building2
                size={17}
                className="text-[#9AA39E]"
              />
            </div>

            <p className="mt-2 text-2xl font-semibold text-[#17211D]">
              {loadingStats
                ? "—"
                : stats?.total_pharmacies ?? "—"}
            </p>

            <p className="mt-1 text-xs text-[#7C8881]">
              Registered organizations
            </p>
          </div>

          <div className="rounded-2xl border border-[#DFE6E1] bg-white p-5">
            <div className="flex items-center justify-between">
              <p className="text-sm text-[#7C8881]">
                Active pharmacies
              </p>

              <Activity
                size={17}
                className="text-[#35664D]"
              />
            </div>

            <p className="mt-2 text-2xl font-semibold text-[#17211D]">
              {loadingStats
                ? "—"
                : stats?.active_pharmacies ?? "—"}
            </p>

            <p className="mt-1 text-xs text-[#7C8881]">
              Currently active
            </p>
          </div>

          <div className="rounded-2xl border border-[#DFE6E1] bg-white p-5">
            <div className="flex items-center justify-between">
              <p className="text-sm text-[#7C8881]">
                Inactive pharmacies
              </p>

              <Users
                size={17}
                className="text-[#9AA39E]"
              />
            </div>

            <p className="mt-2 text-2xl font-semibold text-[#17211D]">
              {loadingStats
                ? "—"
                : stats?.inactive_pharmacies ?? "—"}
            </p>

            <p className="mt-1 text-xs text-[#7C8881]">
              Disabled organizations
            </p>
          </div>
        </section>

        {/* FILTERS */}

        <section className="mt-8 rounded-2xl border border-[#DFE6E1] bg-white p-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center">
            <div className="relative flex-1">
              <Search
                size={18}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9AA39E]"
              />

              <input
                type="text"
                value={search}
                onChange={(event) =>
                  handleSearchChange(event.target.value)
                }
                placeholder="Search pharmacies by name or slug..."
                className="w-full rounded-xl border border-[#DFE6E1] bg-[#FAFCFB] py-2.5 pl-10 pr-4 text-sm text-[#17211D] outline-none transition placeholder:text-[#9AA39E] focus:border-[#AFCDBB]"
              />
            </div>

            <select
              value={statusFilter}
              onChange={(event) =>
                handleStatusChange(
                  event.target.value as
                    | "all"
                    | "active"
                    | "inactive"
                )
              }
              className="rounded-xl border border-[#DFE6E1] bg-[#FAFCFB] px-4 py-2.5 text-sm text-[#526158] outline-none focus:border-[#AFCDBB]"
            >
              <option value="all">All statuses</option>
              <option value="active">Active only</option>
              <option value="inactive">Inactive only</option>
            </select>
          </div>
        </section>

        {/* ERROR */}

        {error && (
          <div className="mt-4 flex flex-col gap-3 rounded-2xl border border-[#F0CACA] bg-[#FFF0F0] px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-medium text-[#A74646]">
                Unable to load pharmacies
              </p>

              <p className="mt-1 text-sm text-[#7C8881]">
                {error}
              </p>
            </div>

            <button
              type="button"
              onClick={loadPharmacies}
              className="inline-flex items-center justify-center rounded-lg border border-[#E4B9B9] bg-white px-3 py-2 text-sm font-medium text-[#A74646] transition hover:bg-[#FFF8F8]"
            >
              Try again
            </button>
          </div>
        )}

        {/* PHARMACY TABLE */}

        <section className="mt-4 overflow-hidden rounded-2xl border border-[#DFE6E1] bg-white">
          <div className="flex flex-col gap-3 border-b border-[#DFE6E1] px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="font-semibold text-[#17211D]">
                Pharmacy organizations
              </h2>

              <p className="mt-1 text-sm text-[#7C8881]">
                Organization activity and platform usage.
              </p>
            </div>

            <div className="text-sm text-[#7C8881]">
              {loadingPharmacies
                ? "Loading..."
                : `${total} ${
                    total === 1
                      ? "pharmacy"
                      : "pharmacies"
                  }`}
            </div>
          </div>

          {loadingPharmacies ? (
            <div className="px-6 py-16">
              <div className="mx-auto max-w-sm">
                <div className="h-4 animate-pulse rounded bg-[#DFE6E1]" />
                <div className="mt-3 h-4 w-4/5 animate-pulse rounded bg-[#F4F7F5]" />
                <div className="mt-3 h-4 w-3/5 animate-pulse rounded bg-[#F4F7F5]" />
              </div>
            </div>
          ) : pharmacies.length === 0 ? (
            <div className="px-6 py-16 text-center">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-[#F4F7F5] text-[#7C8881]">
                <Building2 size={24} />
              </div>

              <h3 className="mt-5 font-semibold text-[#17211D]">
                No pharmacies found
              </h3>

              <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-[#7C8881]">
                No pharmacy organizations match the current
                search and filter criteria.
              </p>

              {(search ||
                statusFilter !== "all") && (
                <button
                  type="button"
                  onClick={() => {
                    setSearch("");
                    setStatusFilter("all");
                    setPage(0);
                  }}
                  className="mt-5 text-sm font-medium text-[#35664D] hover:underline"
                >
                  Clear filters
                </button>
              )}
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[1050px] text-left">
                  <thead className="border-b border-[#DFE6E1] bg-[#FAFCFB]">
                    <tr>
                      <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#7C8881]">
                        Pharmacy
                      </th>

                      <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#7C8881]">
                        Contact
                      </th>

                      <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#7C8881]">
                        Team
                      </th>

                      <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#7C8881]">
                        Prescriptions
                      </th>

                      <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#7C8881]">
                        Status
                      </th>

                      <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#7C8881]">
                        Created
                      </th>
                    </tr>
                  </thead>

                  <tbody>
                    {pharmacies.map((pharmacy) => (
                      <tr
                        key={pharmacy.id}
                        className="border-b border-[#DFE6E1] transition last:border-b-0 hover:bg-[#FAFCFB]"
                      >
                        <td className="px-5 py-4">
                          <div className="flex items-start gap-3">
                            <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#F4F7F5] text-[#526158]">
                              <Building2 size={17} />
                            </div>

                            <div>
                              <p className="font-medium text-[#17211D]">
                                {pharmacy.name}
                              </p>

                              <p className="mt-1 text-xs text-[#9AA39E]">
                                {pharmacy.slug}
                              </p>
                            </div>
                          </div>
                        </td>

                        <td className="px-5 py-4">
                          {pharmacy.email ? (
                            <p className="text-sm text-[#526158]">
                              {pharmacy.email}
                            </p>
                          ) : (
                            <p className="text-sm text-[#9AA39E]">
                              No email
                            </p>
                          )}

                          {pharmacy.phone && (
                            <p className="mt-1 text-xs text-[#7C8881]">
                              {pharmacy.phone}
                            </p>
                          )}
                        </td>

                        <td className="px-5 py-4">
                          <div className="space-y-1">
                            <p className="text-sm text-[#526158]">
                              <span className="font-medium text-[#17211D]">
                                {pharmacy.pharmacist_count}
                              </span>{" "}
                              pharmacist
                              {pharmacy.pharmacist_count === 1
                                ? ""
                                : "s"}
                            </p>

                            <p className="text-xs text-[#7C8881]">
                              {pharmacy.customer_count} customer
                              {pharmacy.customer_count === 1
                                ? ""
                                : "s"}
                            </p>
                          </div>
                        </td>

                        <td className="px-5 py-4">
                          <p className="text-sm font-medium text-[#17211D]">
                            {pharmacy.prescription_count}
                          </p>

                          <p className="mt-1 text-xs text-[#7C8881]">
                            analyzed
                          </p>
                        </td>

                        <td className="px-5 py-4">
                          <span
                            className={`inline-flex rounded-lg border px-2.5 py-1 text-xs font-medium ${statusStyle(
                              pharmacy.is_active
                            )}`}
                          >
                            {pharmacy.is_active
                              ? "Active"
                              : "Inactive"}
                          </span>
                        </td>

                        <td className="px-5 py-4 text-sm text-[#526158]">
                          {formatDate(pharmacy.created_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* PAGINATION */}

              <div className="flex flex-col gap-3 border-t border-[#DFE6E1] px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-sm text-[#7C8881]">
                  Showing{" "}
                  <span className="font-medium text-[#526158]">
                    {page * pageSize + 1}
                  </span>{" "}
                  to{" "}
                  <span className="font-medium text-[#526158]">
                    {Math.min(
                      page * pageSize + pharmacies.length,
                      total
                    )}
                  </span>{" "}
                  of{" "}
                  <span className="font-medium text-[#526158]">
                    {total}
                  </span>
                </p>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={
                      !hasPreviousPage ||
                      loadingPharmacies
                    }
                    onClick={() =>
                      setPage((current) =>
                        Math.max(0, current - 1)
                      )
                    }
                    className="inline-flex items-center gap-1.5 rounded-lg border border-[#DFE6E1] bg-white px-3 py-2 text-sm font-medium text-[#526158] transition hover:border-[#CBE0D3] hover:text-[#35664D] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <ChevronLeft size={16} />
                    Previous
                  </button>

                  <span className="px-2 text-sm text-[#7C8881]">
                    {page + 1} / {totalPages}
                  </span>

                  <button
                    type="button"
                    disabled={
                      !hasNextPage ||
                      loadingPharmacies
                    }
                    onClick={() =>
                      setPage(
                        (current) => current + 1
                      )
                    }
                    className="inline-flex items-center gap-1.5 rounded-lg border border-[#DFE6E1] bg-white px-3 py-2 text-sm font-medium text-[#526158] transition hover:border-[#CBE0D3] hover:text-[#35664D] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Next
                    <ChevronRight size={16} />
                  </button>
                </div>
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  );
}