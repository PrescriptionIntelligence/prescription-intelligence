"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Search,
  ShieldCheck,
  UserRound,
  Users,
} from "lucide-react";

import {
  authFetch,
  fetchMe,
  getUser,
  isAuthenticated,
  User,
} from "../../../lib/auth";

type Role = "admin" | "pharmacist" | "customer";

type UserRow = {
  id: string;
  name: string;
  email: string;
  role: Role;
  is_active: boolean;
  organization: {
    id: string;
    name: string;
    slug: string;
  } | null;
  created_at: string | null;
  last_login_at: string | null;
};

type UsersResponse = {
  items: UserRow[];
  total: number;
  skip: number;
  limit: number;
};

type UserStats = {
  total_users: number;
  active_users: number;
  inactive_users: number;
  pharmacists: number;
  customers: number;
  admins: number;
};

function roleLabel(role: Role) {
  if (role === "admin") return "Administrator";
  if (role === "pharmacist") return "Pharmacist";
  return "Customer";
}

function roleStyle(role: Role) {
  if (role === "admin") {
    return "border-[#CBE0D3] bg-[#EDF8F1] text-[#35664D]";
  }

  if (role === "pharmacist") {
    return "border-[#DFE6E1] bg-[#F4F7F5] text-[#526158]";
  }

  return "border-[#DFE6E1] bg-white text-[#526158]";
}

function statusStyle(isActive: boolean) {
  if (isActive) {
    return "border-[#CBE0D3] bg-[#EDF8F1] text-[#35664D]";
  }

  return "border-[#DFE6E1] bg-[#F4F7F5] text-[#7C8881]";
}

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

export default function AdminUsersPage() {
  const router = useRouter();

  const [user, setUser] = useState<User | null>(null);

  const [loading, setLoading] = useState(true);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [loadingStats, setLoadingStats] = useState(true);

  const [error, setError] = useState("");

  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<"all" | Role>("all");
  const [statusFilter, setStatusFilter] = useState<
    "all" | "active" | "inactive"
  >("all");

  const [users, setUsers] = useState<UserRow[]>([]);
  const [stats, setStats] = useState<UserStats | null>(null);

  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);

  const pageSize = 20;

  /*
   * Authenticate the current workspace user.
   */
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

  /*
   * Load platform-wide user statistics.
   */
  async function loadStats() {
    setLoadingStats(true);

    try {
      const response = await authFetch("/admin/users/stats");

      if (!response.ok) {
        throw new Error("Unable to load user statistics.");
      }

      const data: UserStats = await response.json();

      setStats(data);
    } catch {
      setStats(null);
    } finally {
      setLoadingStats(false);
    }
  }

  /*
   * Load platform users.
   */
  async function loadUsers() {
    setLoadingUsers(true);
    setError("");

    try {
      const params = new URLSearchParams();

      const trimmedSearch = search.trim();

      if (trimmedSearch) {
        params.set("q", trimmedSearch);
      }

      if (roleFilter !== "all") {
        params.set("role", roleFilter);
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
        `/admin/users?${params.toString()}`
      );

      if (!response.ok) {
        if (response.status === 403) {
          router.replace("/dashboard");
          return;
        }

        throw new Error("Unable to load platform users.");
      }

      const data: UsersResponse = await response.json();

      setUsers(data.items ?? []);
      setTotal(data.total ?? 0);
    } catch {
      setUsers([]);
      setTotal(0);
      setError(
        "We couldn't load the platform users. Please try again."
      );
    } finally {
      setLoadingUsers(false);
    }
  }

  /*
   * Load data after admin authentication succeeds.
   */
  useEffect(() => {
    if (!user || user.role !== "admin") {
      return;
    }

    loadStats();
  }, [user]);

  /*
   * Reload users whenever filters or pagination change.
   */
  useEffect(() => {
    if (!user || user.role !== "admin") {
      return;
    }

    const timeout = window.setTimeout(() => {
      loadUsers();
    }, 250);

    return () => {
      window.clearTimeout(timeout);
    };
  }, [user, search, roleFilter, statusFilter, page]);

  function handleSearchChange(value: string) {
    setSearch(value);
    setPage(0);
  }

  function handleRoleChange(value: "all" | Role) {
    setRoleFilter(value);
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
    loadUsers();
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

          <div className="mt-4 h-9 w-64 animate-pulse rounded-lg bg-[#DFE6E1]" />

          <div className="mt-8 grid gap-4 md:grid-cols-3">
            <div className="h-28 animate-pulse rounded-2xl bg-white" />
            <div className="h-28 animate-pulse rounded-2xl bg-white" />
            <div className="h-28 animate-pulse rounded-2xl bg-white" />
          </div>

          <div className="mt-4 h-20 animate-pulse rounded-2xl bg-white" />

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
        {/* Header */}
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
                <Users size={21} />
              </div>

              <div>
                <h1 className="text-3xl font-semibold tracking-tight text-[#17211D]">
                  Users
                </h1>

                <p className="mt-1 text-sm text-[#7C8881]">
                  Manage platform accounts and role assignments.
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={refreshData}
              disabled={loadingUsers || loadingStats}
              className="inline-flex items-center gap-2 rounded-xl border border-[#DFE6E1] bg-white px-3 py-2 text-sm font-medium text-[#526158] transition hover:border-[#CBE0D3] hover:text-[#35664D] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <RefreshCw
                size={15}
                className={
                  loadingUsers || loadingStats
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

        {/* Statistics */}
        <section className="mt-8 grid gap-4 md:grid-cols-3">
          <div className="rounded-2xl border border-[#DFE6E1] bg-white p-5">
            <div className="flex items-center justify-between">
              <p className="text-sm text-[#7C8881]">
                Total users
              </p>

              <Users
                size={17}
                className="text-[#9AA39E]"
              />
            </div>

            <p className="mt-2 text-2xl font-semibold text-[#17211D]">
              {loadingStats
                ? "—"
                : stats?.total_users ?? "—"}
            </p>

            {!loadingStats && stats && (
              <p className="mt-1 text-xs text-[#7C8881]">
                {stats.active_users} active accounts
              </p>
            )}
          </div>

          <div className="rounded-2xl border border-[#DFE6E1] bg-white p-5">
            <div className="flex items-center justify-between">
              <p className="text-sm text-[#7C8881]">
                Pharmacists
              </p>

              <ShieldCheck
                size={17}
                className="text-[#35664D]"
              />
            </div>

            <p className="mt-2 text-2xl font-semibold text-[#17211D]">
              {loadingStats
                ? "—"
                : stats?.pharmacists ?? "—"}
            </p>

            {!loadingStats && stats && (
              <p className="mt-1 text-xs text-[#7C8881]">
                Pharmacy staff accounts
              </p>
            )}
          </div>

          <div className="rounded-2xl border border-[#DFE6E1] bg-white p-5">
            <div className="flex items-center justify-between">
              <p className="text-sm text-[#7C8881]">
                Customers
              </p>

              <UserRound
                size={17}
                className="text-[#526158]"
              />
            </div>

            <p className="mt-2 text-2xl font-semibold text-[#17211D]">
              {loadingStats
                ? "—"
                : stats?.customers ?? "—"}
            </p>

            {!loadingStats && stats && (
              <p className="mt-1 text-xs text-[#7C8881]">
                Patient accounts
              </p>
            )}
          </div>
        </section>

        {/* Search and filters */}
        <section className="mt-8 rounded-2xl border border-[#DFE6E1] bg-white p-4">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
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
                placeholder="Search users by name or email..."
                className="w-full rounded-xl border border-[#DFE6E1] bg-[#FAFCFB] py-2.5 pl-10 pr-4 text-sm text-[#17211D] outline-none transition placeholder:text-[#9AA39E] focus:border-[#AFCDBB]"
              />
            </div>

            <div className="flex flex-col gap-3 sm:flex-row">
              <select
                value={roleFilter}
                onChange={(event) =>
                  handleRoleChange(
                    event.target.value as "all" | Role
                  )
                }
                className="rounded-xl border border-[#DFE6E1] bg-[#FAFCFB] px-4 py-2.5 text-sm text-[#526158] outline-none focus:border-[#AFCDBB]"
              >
                <option value="all">All roles</option>
                <option value="admin">Administrators</option>
                <option value="pharmacist">Pharmacists</option>
                <option value="customer">Customers</option>
              </select>

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
          </div>
        </section>

        {/* Error */}
        {error && (
          <div className="mt-4 flex flex-col gap-3 rounded-2xl border border-[#F0CACA] bg-[#FFF0F0] px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-medium text-[#A74646]">
                Unable to load users
              </p>

              <p className="mt-1 text-sm text-[#7C8881]">
                {error}
              </p>
            </div>

            <button
              type="button"
              onClick={loadUsers}
              className="inline-flex items-center justify-center rounded-lg border border-[#E4B9B9] bg-white px-3 py-2 text-sm font-medium text-[#A74646] transition hover:bg-[#FFF8F8]"
            >
              Try again
            </button>
          </div>
        )}

        {/* User table */}
        <section className="mt-4 overflow-hidden rounded-2xl border border-[#DFE6E1] bg-white">
          <div className="flex flex-col gap-3 border-b border-[#DFE6E1] px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="font-semibold text-[#17211D]">
                Platform accounts
              </h2>

              <p className="mt-1 text-sm text-[#7C8881]">
                Role and account information for registered users.
              </p>
            </div>

            <div className="text-sm text-[#7C8881]">
              {loadingUsers
                ? "Loading..."
                : `${total} ${
                    total === 1 ? "account" : "accounts"
                  }`}
            </div>
          </div>

          {loadingUsers ? (
            <div className="px-6 py-16">
              <div className="mx-auto max-w-sm">
                <div className="h-4 animate-pulse rounded bg-[#DFE6E1]" />
                <div className="mt-3 h-4 w-4/5 animate-pulse rounded bg-[#F4F7F5]" />
                <div className="mt-3 h-4 w-3/5 animate-pulse rounded bg-[#F4F7F5]" />
              </div>
            </div>
          ) : users.length === 0 ? (
            <div className="px-6 py-16 text-center">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-[#F4F7F5] text-[#7C8881]">
                <UserRound size={24} />
              </div>

              <h3 className="mt-5 font-semibold text-[#17211D]">
                No users found
              </h3>

              <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-[#7C8881]">
                No platform accounts match the current search
                and filter criteria.
              </p>

              {(search ||
                roleFilter !== "all" ||
                statusFilter !== "all") && (
                <button
                  type="button"
                  onClick={() => {
                    setSearch("");
                    setRoleFilter("all");
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
                <table className="w-full min-w-[900px] text-left">
                  <thead className="border-b border-[#DFE6E1] bg-[#FAFCFB]">
                    <tr>
                      <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#7C8881]">
                        User
                      </th>

                      <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#7C8881]">
                        Role
                      </th>

                      <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#7C8881]">
                        Organization
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
                    {users.map((item) => (
                      <tr
                        key={item.id}
                        className="border-b border-[#DFE6E1] transition last:border-b-0 hover:bg-[#FAFCFB]"
                      >
                        <td className="px-5 py-4">
                          <p className="font-medium text-[#17211D]">
                            {item.name}
                          </p>

                          <p className="mt-1 text-sm text-[#7C8881]">
                            {item.email}
                          </p>
                        </td>

                        <td className="px-5 py-4">
                          <span
                            className={`inline-flex rounded-lg border px-2.5 py-1 text-xs font-medium ${roleStyle(
                              item.role
                            )}`}
                          >
                            {roleLabel(item.role)}
                          </span>
                        </td>

                        <td className="px-5 py-4">
                          {item.organization ? (
                            <>
                              <p className="text-sm font-medium text-[#526158]">
                                {item.organization.name}
                              </p>

                              <p className="mt-1 text-xs text-[#9AA39E]">
                                {item.organization.slug}
                              </p>
                            </>
                          ) : (
                            <span className="text-sm text-[#9AA39E]">
                              No organization
                            </span>
                          )}
                        </td>

                        <td className="px-5 py-4">
                          <span
                            className={`inline-flex rounded-lg border px-2.5 py-1 text-xs font-medium ${statusStyle(
                              item.is_active
                            )}`}
                          >
                            {item.is_active
                              ? "Active"
                              : "Inactive"}
                          </span>
                        </td>

                        <td className="px-5 py-4 text-sm text-[#526158]">
                          {formatDate(item.created_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <div className="flex flex-col gap-3 border-t border-[#DFE6E1] px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-sm text-[#7C8881]">
                  Showing{" "}
                  <span className="font-medium text-[#526158]">
                    {page * pageSize + 1}
                  </span>{" "}
                  to{" "}
                  <span className="font-medium text-[#526158]">
                    {Math.min(
                      page * pageSize + users.length,
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
                    disabled={!hasPreviousPage || loadingUsers}
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
                    disabled={!hasNextPage || loadingUsers}
                    onClick={() =>
                      setPage((current) => current + 1)
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