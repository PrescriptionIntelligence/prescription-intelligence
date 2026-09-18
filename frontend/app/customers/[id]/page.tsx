"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { authFetch, isAuthenticated, isPharmacist } from "@/lib/auth";
import AppShell from "@/components/AppShell";

// =========================================================
// Types
// =========================================================

type Pharmacy = {
  id: string;
  name: string;
  slug: string;
};

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
  organization_id: string;
  created_at: string;
  updated_at: string;
  prescription_count: number;
  pharmacies: Pharmacy[];
};

type Prescription = {
  prescription_id: string;
  file_name: string | null;
  status: string;
  review_status: string;
  created_at: string;
  safety_flags: { severity: string }[];
  medicines: { id: string }[];
};

// =========================================================
// Helpers
// =========================================================

function formatDate(iso: string | null): string {
  if (!iso) return "—";
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

function formatDateTime(iso: string): string {
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

function reviewBadge(status: string) {
  const s = status.toLowerCase();
  if (s === "verified")
    return "bg-[#edf8f1] text-[#2d6444] border-[#cce3d4]";
  if (s === "rejected")
    return "bg-[#fff0f0] text-[#7b2929] border-[#eccaca]";
  if (s === "reviewed")
    return "bg-[#edf4fb] text-[#1e4b8c] border-[#c8daf5]";
  return "bg-[#fff7df] text-[#705617] border-[#ebdcae]";
}

// =========================================================
// Detail row helper
// =========================================================

function DetailRow({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5">
      <span className="text-xs font-medium text-[#7b8580]">{label}</span>
      <span className="text-right text-xs text-[#17211d]">{value || "—"}</span>
    </div>
  );
}

// =========================================================
// Component
// =========================================================

export default function CustomerDetailPage() {
  const params = useParams();
  const router = useRouter();

  const customerId = params?.id as string;

  const [customer, setCustomer] = useState<Customer | null>(null);
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [rxLoading, setRxLoading] = useState(false);
  const [rxSkip, setRxSkip] = useState(0);
  const [rxHasMore, setRxHasMore] = useState(false);
  const [rxLoadingMore, setRxLoadingMore] = useState(false);
  const RX_PAGE = 20;

  // ----------------------------------------------------------
  // Auth guard
  // ----------------------------------------------------------

  useEffect(() => {
    if (!isAuthenticated() || !isPharmacist()) {
      router.replace("/sign-in");
    }
  }, [router]);

  // ----------------------------------------------------------
  // Load customer
  // ----------------------------------------------------------

  useEffect(() => {
    if (!customerId || !isAuthenticated() || !isPharmacist()) return;

    authFetch(`/customers/${encodeURIComponent(customerId)}`)
      .then((response) => {
        if (!response.ok) throw new Error("Customer not found");
        return response.json();
      })
      .then((data: Customer) => {
        setCustomer(data);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load customer");
      })
      .finally(() => setLoading(false));
  }, [customerId]);

  // ----------------------------------------------------------
  // Load prescriptions (paginated)
  // ----------------------------------------------------------

  async function loadPrescriptions(offset: number, replace: boolean) {
    if (offset === 0) setRxLoading(true);
    else setRxLoadingMore(true);

    try {
      const response = await authFetch(
        `/customers/${encodeURIComponent(customerId)}/prescriptions?skip=${offset}&limit=${RX_PAGE}`
      );
      if (!response.ok) return;
      const data: Prescription[] = await response.json();
      if (replace) {
        setPrescriptions(data);
      } else {
        setPrescriptions((prev) => [...prev, ...data]);
      }
      setRxHasMore(data.length === RX_PAGE);
      setRxSkip(offset + data.length);
    } catch {
      // Non-fatal
    } finally {
      setRxLoading(false);
      setRxLoadingMore(false);
    }
  }

  useEffect(() => {
    if (!customer || !isAuthenticated()) return;
    loadPrescriptions(0, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customer, customerId]);

  // ----------------------------------------------------------
  // Loading state
  // ----------------------------------------------------------

  if (loading) {
    return (
      <AppShell>
        <div className="flex items-center gap-2 px-8 py-10 text-sm text-[#68766f]">
          <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-[#cfd8d3] border-t-[#17211d]" />
          Loading customer…
        </div>
      </AppShell>
    );
  }

  if (error || !customer) {
    return (
      <AppShell>
        <div className="mx-auto max-w-md px-8 py-16 text-center">
          <p className="text-sm font-medium text-[#344139]">
            {error || "Customer not found"}
          </p>
          <Link
            href="/customers"
            className="mt-4 inline-block text-xs text-[#35664d] hover:text-[#17211d]"
          >
            ← Back to customers
          </Link>
        </div>
      </AppShell>
    );
  }

  const highCount = prescriptions.reduce(
    (count, rx) =>
      count +
      rx.safety_flags.filter(
        (f) => f.severity === "high" || f.severity === "error"
      ).length,
    0
  );

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl px-5 py-8 sm:px-8">

        {/* Breadcrumb */}
        <div className="mb-5 flex items-center gap-2 text-[11px] text-[#8b9690]">
          <Link href="/customers" className="transition hover:text-[#17211d]">
            Customers
          </Link>
          <span>/</span>
          <span className="text-[#4d5b53]">{customer.name}</span>
        </div>

        {/* Header */}
        <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-[-0.03em] text-[#17211d]">
                {customer.name}
              </h1>
              <span className="rounded-md bg-[#f0f4f1] px-2 py-0.5 font-mono text-[10px] text-[#52645a]">
                {customer.customer_code}
              </span>
              {!customer.is_active && (
                <span className="rounded-full bg-[#fff0f0] px-2 py-0.5 text-[10px] font-medium text-[#8b4040]">
                  Inactive
                </span>
              )}
            </div>
            <p className="mt-1 text-sm text-[#7b8580]">
              Customer profile · {customer.prescription_count} prescription
              {customer.prescription_count !== 1 ? "s" : ""}
            </p>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">

          {/* ===================================================
              Left: Profile details
          =================================================== */}

          <aside className="space-y-5">

            {/* Contact details */}
            <section className="rounded-2xl border border-[#dfe6e1] bg-white p-5 shadow-[0_5px_25px_rgba(28,46,36,0.035)]">
              <p className="mb-2 text-xs font-semibold text-[#344139]">
                Profile
              </p>
              <div className="divide-y divide-[#edf0ee]">
                <DetailRow label="Phone" value={customer.phone} />
                <DetailRow label="Email" value={customer.email} />
                <DetailRow
                  label="Date of birth"
                  value={formatDate(customer.date_of_birth)}
                />
                <DetailRow label="Address" value={customer.address} />
                <DetailRow
                  label="Added"
                  value={formatDate(customer.created_at)}
                />
              </div>
            </section>

            {/* Notes */}
            {customer.notes && (
              <section className="rounded-2xl border border-[#dfe6e1] bg-white p-5 shadow-[0_5px_25px_rgba(28,46,36,0.035)]">
                <p className="mb-2 text-xs font-semibold text-[#344139]">
                  Notes
                </p>
                <p className="text-xs leading-5 text-[#526158]">
                  {customer.notes}
                </p>
              </section>
            )}

            {/* Connected pharmacies */}
            {customer.pharmacies.length > 0 && (
              <section className="rounded-2xl border border-[#dfe6e1] bg-white p-5 shadow-[0_5px_25px_rgba(28,46,36,0.035)]">
                <p className="mb-3 text-xs font-semibold text-[#344139]">
                  Connected pharmacies
                </p>
                <ul className="space-y-2">
                  {customer.pharmacies.map((pharmacy) => (
                    <li
                      key={pharmacy.id}
                      className="flex items-center gap-2 text-xs"
                    >
                      <span className="h-1.5 w-1.5 rounded-full bg-[#3f7658]" />
                      <span className="font-medium text-[#17211d]">
                        {pharmacy.name}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* Safety summary */}
            {prescriptions.length > 0 && (
              <section className="rounded-2xl border border-[#dfe6e1] bg-white p-5 shadow-[0_5px_25px_rgba(28,46,36,0.035)]">
                <p className="mb-3 text-xs font-semibold text-[#344139]">
                  Safety summary
                </p>
                <div className="divide-y divide-[#edf0ee]">
                  <DetailRow
                    label="Prescriptions"
                    value={String(prescriptions.length)}
                  />
                  <DetailRow
                    label="High-priority findings"
                    value={
                      highCount > 0
                        ? `${highCount} finding${highCount === 1 ? "" : "s"}`
                        : "None"
                    }
                  />
                </div>
              </section>
            )}
          </aside>

          {/* ===================================================
              Right: Prescriptions
          =================================================== */}

          <section>
            <div className="mb-3 flex items-center justify-between">
              <p className="text-xs font-semibold text-[#344139]">
                Prescriptions
              </p>
              {rxLoading && (
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-[#cfd8d3] border-t-[#17211d]" />
              )}
            </div>

            {!rxLoading && prescriptions.length === 0 ? (
              <div className="rounded-2xl border border-[#dfe6e1] bg-white p-8 text-center">
                <p className="text-sm font-medium text-[#344139]">
                  No prescriptions
                </p>
                <p className="mt-1 text-xs text-[#7b8580]">
                  No prescriptions have been assigned to this customer yet.
                </p>
              </div>
            ) : (
              <div className="overflow-hidden rounded-2xl border border-[#dfe6e1] bg-white shadow-[0_5px_25px_rgba(28,46,36,0.035)]">
                <ul className="divide-y divide-[#edf0ee]">
                  {prescriptions.map((rx) => {
                    const rxHighCount = rx.safety_flags.filter(
                      (f) => f.severity === "high" || f.severity === "error"
                    ).length;

                    return (
                      <li key={rx.prescription_id}>
                        <Link
                          href={`/analysis/${encodeURIComponent(rx.prescription_id)}`}
                          className="flex items-center justify-between px-5 py-4 transition hover:bg-[#f9faf9]"
                        >
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-mono text-[11px] font-medium text-[#4d5b53]">
                                {rx.prescription_id}
                              </span>
                              <span
                                className={`rounded-full border px-2 py-0.5 text-[10px] font-medium capitalize ${reviewBadge(
                                  rx.review_status
                                )}`}
                              >
                                {rx.review_status}
                              </span>
                              {rxHighCount > 0 && (
                                <span className="rounded-full border border-[#e7caca] bg-[#fff0f0] px-2 py-0.5 text-[10px] font-medium text-[#a74646]">
                                  {rxHighCount} high
                                </span>
                              )}
                            </div>

                            <div className="mt-1 flex flex-wrap items-center gap-3">
                              {rx.file_name && (
                                <span className="text-[11px] text-[#7b8580]">
                                  {rx.file_name}
                                </span>
                              )}
                              <span className="text-[11px] text-[#9aa39e]">
                                {formatDateTime(rx.created_at)}
                              </span>
                              <span className="text-[11px] text-[#9aa39e]">
                                {rx.medicines.length} medicine
                                {rx.medicines.length !== 1 ? "s" : ""}
                              </span>
                            </div>
                          </div>

                          <span className="ml-4 shrink-0 text-xs text-[#9aa39e]">→</span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
                {rxHasMore && (
                  <div className="border-t border-[#edf0ee] px-5 py-4 text-center">
                    <button
                      type="button"
                      onClick={() => loadPrescriptions(rxSkip, false)}
                      disabled={rxLoadingMore}
                      className="text-xs font-medium text-[#526c5d] hover:underline disabled:opacity-50"
                    >
                      {rxLoadingMore ? "Loading…" : "Load more"}
                    </button>
                  </div>
                )}
              </div>
            )}
          </section>
        </div>
      </div>
    </AppShell>
  );
}
