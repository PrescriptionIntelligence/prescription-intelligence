"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { authFetch, isAuthenticated, isPharmacist } from "@/lib/auth";
import AppShell from "@/components/AppShell";

// =========================================================
// Types
// =========================================================

type Customer = {
  id: string;
  customer_code: string;
  name: string;
  phone: string | null;
  email: string | null;
  date_of_birth: string | null;
  address: string | null;
  notes: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

type CreateForm = {
  name: string;
  phone: string;
  email: string;
  date_of_birth: string;
  address: string;
  notes: string;
};

// =========================================================
// Helpers
// =========================================================

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

const EMPTY_FORM: CreateForm = {
  name: "",
  phone: "",
  email: "",
  date_of_birth: "",
  address: "",
  notes: "",
};

// =========================================================
// Component
// =========================================================

export default function CustomersPage() {
  const router = useRouter();

  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [skip, setSkip] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<Customer[] | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<CreateForm>(EMPTY_FORM);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [createSuccess, setCreateSuccess] = useState("");

  // ----------------------------------------------------------
  // Auth guard
  // ----------------------------------------------------------

  useEffect(() => {
    if (!isAuthenticated() || !isPharmacist()) {
      router.replace("/sign-in");
    }
  }, [router]);

  // ----------------------------------------------------------
  // Load customer list
  // ----------------------------------------------------------

  const PAGE_SIZE = 20;

  async function loadCustomers(offset: number, replace: boolean) {
    if (offset === 0) setLoading(true);
    else setLoadingMore(true);

    try {
      const response = await authFetch(`/customers?skip=${offset}&limit=${PAGE_SIZE}`);
      if (!response.ok) throw new Error("Failed to load customers");
      const data: Customer[] = await response.json();
      if (replace) {
        setCustomers(data);
      } else {
        setCustomers((prev) => [...prev, ...data]);
      }
      setHasMore(data.length === PAGE_SIZE);
      setSkip(offset + data.length);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load customers");
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }

  useEffect(() => {
    if (!isAuthenticated() || !isPharmacist()) return;
    loadCustomers(0, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ----------------------------------------------------------
  // Search
  // ----------------------------------------------------------

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = searchQuery.trim();

    if (!query) {
      setSearchResults(null);
      return;
    }

    setSearching(true);

    try {
      const response = await authFetch(
        `/customers/search?q=${encodeURIComponent(query)}`
      );

      if (!response.ok) throw new Error("Search failed");

      const data: Customer[] = await response.json();
      setSearchResults(data);
    } catch {
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  }

  function clearSearch() {
    setSearchQuery("");
    setSearchResults(null);
  }

  // ----------------------------------------------------------
  // Create customer
  // ----------------------------------------------------------

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreateError("");
    setCreateSuccess("");

    const name = form.name.trim();
    if (!name) {
      setCreateError("Customer name is required.");
      return;
    }

    setCreating(true);

    try {
      const payload: Record<string, string | null> = { name };
      if (form.phone.trim()) payload.phone = form.phone.trim();
      if (form.email.trim()) payload.email = form.email.trim();
      if (form.date_of_birth.trim()) payload.date_of_birth = form.date_of_birth.trim();
      if (form.address.trim()) payload.address = form.address.trim();
      if (form.notes.trim()) payload.notes = form.notes.trim();

      const response = await authFetch("/customers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          typeof data?.detail === "string" ? data.detail : "Failed to create customer"
        );
      }

      const newCustomer: Customer = data;
      setCustomers((prev) => [newCustomer, ...prev]);
      setCreateSuccess(`Customer "${newCustomer.name}" created successfully.`);
      setForm(EMPTY_FORM);

      setTimeout(() => {
        setShowCreate(false);
        setCreateSuccess("");
      }, 1800);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create customer");
    } finally {
      setCreating(false);
    }
  }

  // ----------------------------------------------------------
  // Render
  // ----------------------------------------------------------

  const displayList = searchResults !== null ? searchResults : customers;

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl px-5 py-8 sm:px-8">

        {/* Header */}
        <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-[-0.03em] text-[#17211d]">
              Customers
            </h1>
            <p className="mt-1 text-sm text-[#7b8580]">
              Manage pharmacy customer profiles and prescription history.
            </p>
          </div>

          <button
            type="button"
            onClick={() => {
              setShowCreate((v) => !v);
              setCreateError("");
              setCreateSuccess("");
              setForm(EMPTY_FORM);
            }}
            className="rounded-xl bg-[#17211d] px-4 py-2.5 text-xs font-semibold text-white transition hover:bg-[#26332d]"
          >
            {showCreate ? "Cancel" : "+ New customer"}
          </button>
        </div>

        {/* Create form */}
        {showCreate && (
          <section className="mb-6 rounded-2xl border border-[#dfe6e1] bg-white p-6 shadow-[0_5px_25px_rgba(28,46,36,0.04)]">
            <h2 className="mb-4 text-sm font-semibold text-[#17211d]">
              New customer
            </h2>

            {createSuccess && (
              <div className="mb-4 rounded-xl border border-[#d9e5dd] bg-[#f3f8f4] px-4 py-3 text-xs text-[#2d6444]">
                {createSuccess}
              </div>
            )}

            {createError && (
              <div className="mb-4 rounded-xl border border-[#ead8d2] bg-[#fbf5f2] px-4 py-3 text-xs text-[#8b5547]">
                {createError}
              </div>
            )}

            <form onSubmit={handleCreate} className="grid gap-4 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <label className="mb-1.5 block text-xs font-medium text-[#46534c]">
                  Full name <span className="text-[#a74646]">*</span>
                </label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  disabled={creating}
                  placeholder="Patient full name"
                  className="w-full rounded-xl border border-[#d9e1dc] bg-[#fafcfb] px-4 py-2.5 text-sm outline-none focus:border-[#82988b] focus:ring-2 focus:ring-[#e5ece7] disabled:opacity-60"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium text-[#46534c]">Phone</label>
                <input
                  type="tel"
                  value={form.phone}
                  onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
                  disabled={creating}
                  placeholder="+1 555 000 0000"
                  className="w-full rounded-xl border border-[#d9e1dc] bg-[#fafcfb] px-4 py-2.5 text-sm outline-none focus:border-[#82988b] focus:ring-2 focus:ring-[#e5ece7] disabled:opacity-60"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium text-[#46534c]">Email</label>
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                  disabled={creating}
                  placeholder="patient@example.com"
                  className="w-full rounded-xl border border-[#d9e1dc] bg-[#fafcfb] px-4 py-2.5 text-sm outline-none focus:border-[#82988b] focus:ring-2 focus:ring-[#e5ece7] disabled:opacity-60"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium text-[#46534c]">
                  Date of birth
                </label>
                <input
                  type="date"
                  value={form.date_of_birth}
                  onChange={(e) => setForm((f) => ({ ...f, date_of_birth: e.target.value }))}
                  disabled={creating}
                  className="w-full rounded-xl border border-[#d9e1dc] bg-[#fafcfb] px-4 py-2.5 text-sm outline-none focus:border-[#82988b] focus:ring-2 focus:ring-[#e5ece7] disabled:opacity-60"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium text-[#46534c]">Address</label>
                <input
                  type="text"
                  value={form.address}
                  onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))}
                  disabled={creating}
                  placeholder="Street address"
                  className="w-full rounded-xl border border-[#d9e1dc] bg-[#fafcfb] px-4 py-2.5 text-sm outline-none focus:border-[#82988b] focus:ring-2 focus:ring-[#e5ece7] disabled:opacity-60"
                />
              </div>

              <div className="sm:col-span-2">
                <label className="mb-1.5 block text-xs font-medium text-[#46534c]">Notes</label>
                <textarea
                  value={form.notes}
                  onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                  disabled={creating}
                  rows={2}
                  placeholder="Optional notes"
                  className="w-full resize-none rounded-xl border border-[#d9e1dc] bg-[#fafcfb] px-4 py-2.5 text-sm outline-none focus:border-[#82988b] focus:ring-2 focus:ring-[#e5ece7] disabled:opacity-60"
                />
              </div>

              <div className="sm:col-span-2">
                <button
                  type="submit"
                  disabled={creating}
                  className="rounded-xl bg-[#17211d] px-5 py-2.5 text-xs font-semibold text-white transition hover:bg-[#26332d] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {creating ? "Creating…" : "Create customer"}
                </button>
              </div>
            </form>
          </section>
        )}

        {/* Search */}
        <form onSubmit={handleSearch} className="mb-6 flex gap-2">
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by name, code, phone, or email…"
            className="flex-1 rounded-xl border border-[#d9e1dc] bg-white px-4 py-2.5 text-sm outline-none focus:border-[#82988b] focus:ring-2 focus:ring-[#e5ece7]"
          />
          <button
            type="submit"
            disabled={searching}
            className="rounded-xl bg-[#17211d] px-4 py-2.5 text-xs font-semibold text-white transition hover:bg-[#26332d] disabled:opacity-60"
          >
            {searching ? "…" : "Search"}
          </button>
          {searchResults !== null && (
            <button
              type="button"
              onClick={clearSearch}
              className="rounded-xl border border-[#d9e1dc] bg-white px-4 py-2.5 text-xs font-medium text-[#526158] transition hover:bg-[#f4f7f5]"
            >
              Clear
            </button>
          )}
        </form>

        {/* Customer list */}
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-[#68766f]">
            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-[#cfd8d3] border-t-[#17211d]" />
            Loading customers…
          </div>
        ) : error ? (
          <div className="rounded-xl border border-[#ead8d2] bg-[#fbf5f2] px-4 py-3 text-sm text-[#8b5547]">
            {error}
          </div>
        ) : displayList.length === 0 ? (
          <div className="rounded-2xl border border-[#dfe6e1] bg-white p-10 text-center">
            <p className="text-sm font-medium text-[#344139]">
              {searchResults !== null ? "No customers found" : "No customers yet"}
            </p>
            <p className="mt-1 text-xs text-[#7b8580]">
              {searchResults !== null
                ? "Try a different search term."
                : "Create your first customer using the button above."}
            </p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-2xl border border-[#dfe6e1] bg-white shadow-[0_5px_25px_rgba(28,46,36,0.04)]">
            <div className="border-b border-[#edf0ee] px-5 py-3.5">
              <span className="text-xs font-medium text-[#526158]">
                {searchResults !== null
                  ? `${displayList.length} result${displayList.length === 1 ? "" : "s"}`
                  : `${displayList.length} customer${displayList.length === 1 ? "" : "s"}`}
              </span>
            </div>

            <ul className="divide-y divide-[#edf0ee]">
              {displayList.map((customer) => (
                <li key={customer.id}>
                  <Link
                    href={`/customers/${customer.id}`}
                    className="flex items-center justify-between px-5 py-4 transition hover:bg-[#f9faf9]"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-[#17211d]">
                          {customer.name}
                        </span>
                        <span className="rounded-md bg-[#f0f4f1] px-2 py-0.5 font-mono text-[10px] text-[#52645a]">
                          {customer.customer_code}
                        </span>
                        {!customer.is_active && (
                          <span className="rounded-full bg-[#fff0f0] px-2 py-0.5 text-[10px] font-medium text-[#8b4040]">
                            Inactive
                          </span>
                        )}
                      </div>

                      <div className="mt-1 flex flex-wrap items-center gap-3">
                        {customer.phone && (
                          <span className="text-xs text-[#7b8580]">
                            {customer.phone}
                          </span>
                        )}
                        {customer.email && (
                          <span className="text-xs text-[#7b8580]">
                            {customer.email}
                          </span>
                        )}
                        <span className="text-[11px] text-[#9aa39e]">
                          Added {formatDate(customer.created_at)}
                        </span>
                      </div>
                    </div>

                    <span className="ml-4 shrink-0 text-xs text-[#9aa39e]">→</span>
                  </Link>
                </li>
              ))}
            </ul>
            {hasMore && searchResults === null && (
              <div className="border-t border-[#edf0ee] px-5 py-4 text-center">
                <button
                  type="button"
                  onClick={() => loadCustomers(skip, false)}
                  disabled={loadingMore}
                  className="text-xs font-medium text-[#526c5d] hover:underline disabled:opacity-50"
                >
                  {loadingMore ? "Loading…" : "Load more"}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}
