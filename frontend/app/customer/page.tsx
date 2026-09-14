"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  authFetch,
  fetchMe,
  getUser,
  isAuthenticated,
  logout,
  User,
} from "../../lib/auth";

// =========================================================
// Types
// =========================================================

type CustomerProfile = {
  id: string;
  customer_code: string;
  name: string;
  phone: string | null;
  email: string | null;
};

type Pharmacy = {
  id: string;
  name: string;
  slug: string;
};

type Medicine = {
  id?: string;
  medicine_name?: string | null;
  name?: string | null;
  strength?: string | null;
  dosage?: string | null;
  dose?: string | null;
  frequency?: string | null;
  duration?: string | null;
  status?: string | null;
};

type Prescription = {
  id?: string;
  prescription_id?: string;
  file_name?: string | null;
  created_at?: string;
  status?: string | null;
  review_status?: string | null;
  medicines?: Medicine[];
  safety_flags?: unknown[];
  safety_count?: number;
};

type CustomerResponse = {
  profile_linked?: boolean;
  customer?: CustomerProfile | null;
  pharmacies?: Pharmacy[];
};

type PrescriptionResponse = {
  prescriptions?: Prescription[];
  total?: number;
  skip?: number;
  limit?: number;
};

// =========================================================
// Helpers
// =========================================================

function formatDate(value?: string): string {
  if (!value) return "Date unavailable";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Date unavailable";
  }

  return date.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function getPrescriptionId(prescription: Prescription): string {
  return (
    prescription.prescription_id ||
    prescription.id ||
    "unknown"
  );
}

function getMedicineName(medicine: Medicine): string {
  return (
    medicine.medicine_name ||
    medicine.name ||
    "Medicine"
  );
}

function getMedicineDetails(medicine: Medicine): string {
  const parts = [
    medicine.strength,
    medicine.dosage || medicine.dose,
    medicine.frequency,
  ].filter(Boolean);

  return parts.join(" · ");
}

function getPrescriptionStatus(
  prescription: Prescription
): {
  label: string;
  description: string;
  tone: "verified" | "review" | "processing" | "neutral";
} {
  const reviewStatus = (
    prescription.review_status ||
    ""
  ).toLowerCase();

  const status = (
    prescription.status ||
    ""
  ).toLowerCase();

  if (
    reviewStatus === "verified" ||
    status === "verified"
  ) {
    return {
      label: "Verified",
      description: "Reviewed by a pharmacist",
      tone: "verified",
    };
  }

  if (
    reviewStatus === "under_review" ||
    reviewStatus === "needs_clarification" ||
    reviewStatus === "pending" ||
    status === "needs_review"
  ) {
    return {
      label: "Review required",
      description: "Pharmacist verification recommended",
      tone: "review",
    };
  }

  if (
    status === "uploaded" ||
    status === "processing" ||
    status === "analyzing"
  ) {
    return {
      label: "Processing",
      description: "Your prescription is being analyzed",
      tone: "processing",
    };
  }

  return {
    label: "Available",
    description: "Prescription record available",
    tone: "neutral",
  };
}

function statusClasses(
  tone: "verified" | "review" | "processing" | "neutral"
): string {
  switch (tone) {
    case "verified":
      return "border-[#CBE0D3] bg-[#EDF8F1] text-[#35664D]";

    case "review":
      return "border-[#E9D9AE] bg-[#FFF7DF] text-[#A47B2C]";

    case "processing":
      return "border-[#DDE5E1] bg-[#F3F7F5] text-[#526158]";

    default:
      return "border-[#DFE6E1] bg-[#FAFCFB] text-[#526158]";
  }
}

// =========================================================
// Page
// =========================================================

export default function CustomerDashboardPage() {
  const router = useRouter();

  const [user, setUser] = useState<User | null>(null);
  const [customer, setCustomer] =
    useState<CustomerProfile | null>(null);

  const [pharmacies, setPharmacies] = useState<Pharmacy[]>([]);
  const [prescriptions, setPrescriptions] =
    useState<Prescription[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadCustomerWorkspace() {
      if (!isAuthenticated()) {
        router.replace("/sign-in");
        return;
      }

      const storedUser = getUser();

      if (!storedUser) {
        router.replace("/sign-in");
        return;
      }

      if (storedUser.role !== "customer") {
        router.replace("/dashboard");
        return;
      }

      try {
        const freshUser = await fetchMe();

        if (cancelled) return;

        if (freshUser.role !== "customer") {
          router.replace("/dashboard");
          return;
        }

        setUser(freshUser);

        const customerResponse = await authFetch(
          "/customers/me"
        );

        if (!customerResponse.ok) {
          throw new Error(
            "Unable to load your customer profile."
          );
        }

        const customerData: CustomerResponse =
          await customerResponse.json();

        if (cancelled) return;

        setCustomer(customerData.customer ?? null);
        setPharmacies(customerData.pharmacies ?? []);

        const prescriptionsResponse = await authFetch(
          "/customers/me/prescriptions?skip=0&limit=20"
        );

        if (!prescriptionsResponse.ok) {
          throw new Error(
            "Unable to load your prescriptions."
          );
        }

        const prescriptionData: PrescriptionResponse =
          await prescriptionsResponse.json();

        if (cancelled) return;

        setPrescriptions(
          prescriptionData.prescriptions ??
            (Array.isArray(prescriptionData)
              ? prescriptionData
              : [])
        );
      } catch (err) {
        if (cancelled) return;

        setError(
          err instanceof Error
            ? err.message
            : "Something went wrong while loading your workspace."
        );
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadCustomerWorkspace();

    return () => {
      cancelled = true;
    };
  }, [router]);

  const medicationCount = useMemo(() => {
    const names = new Set<string>();

    prescriptions.forEach((prescription) => {
      (prescription.medicines ?? []).forEach((medicine) => {
        names.add(getMedicineName(medicine).toLowerCase());
      });
    });

    return names.size;
  }, [prescriptions]);

  const latestPrescription = prescriptions[0] ?? null;

  const reviewCount = useMemo(() => {
    return prescriptions.filter((prescription) => {
      const result = getPrescriptionStatus(prescription);
      return result.tone === "review";
    }).length;
  }, [prescriptions]);

  const firstName =
    user?.name?.trim().split(/\s+/)[0] || "there";

  // =========================================================
  // Loading
  // =========================================================

  if (loading) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#F4F7F5]">
        <div className="flex items-center gap-3 text-sm text-[#718078]">
          <span className="h-2 w-2 animate-pulse rounded-full bg-[#35664D]" />
          Loading your medication workspace…
        </div>
      </main>
    );
  }

  // =========================================================
  // Main
  // =========================================================

  return (
    <main className="min-h-screen bg-[#F4F7F5] text-[#17211D]">
      {/* =====================================================
          HEADER
          ===================================================== */}

      <header className="border-b border-[#DFE6E1] bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <Link
            href="/customer"
            className="flex items-center gap-3"
          >
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-[#17211D] text-xs font-semibold text-white">
              Rx
            </span>

            <div>
              <div className="text-sm font-semibold">
                Prescription Intelligence
              </div>

              <div className="text-[9px] uppercase tracking-[0.18em] text-[#82908A]">
                Your medication companion
              </div>
            </div>
          </Link>

          <nav className="hidden items-center gap-7 md:flex">
            <Link
              href="/customer"
              className="text-xs font-medium text-[#17211D]"
            >
              Overview
            </Link>

            <Link
              href="/customer/prescriptions"
              className="text-xs text-[#637069] transition hover:text-[#17211D]"
            >
              Prescriptions
            </Link>

            <Link
              href="/customer/profile"
              className="text-xs text-[#637069] transition hover:text-[#17211D]"
            >
              Profile
            </Link>
          </nav>

          <div className="flex items-center gap-4">
            <div className="hidden text-right sm:block">
              <div className="text-xs font-medium">
                {user?.name}
              </div>

              <div className="text-[10px] text-[#8A948F]">
                Patient account
              </div>
            </div>

            <button
              onClick={logout}
              className="rounded-xl border border-[#DCE3DE] bg-white px-4 py-2 text-xs font-medium text-[#53625A] transition hover:border-[#BBC7BF] hover:bg-[#FAFCFB]"
            >
              Log out
            </button>
          </div>
        </div>
      </header>

      {/* =====================================================
          CONTENT
          ===================================================== */}

      <section className="mx-auto max-w-7xl px-6 py-10">
        {/* Error */}
        {error && (
          <div className="mb-7 rounded-2xl border border-[#E8D2D2] bg-[#FFF5F5] px-5 py-4">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-[#FBE7E7] text-sm text-[#A74646]">
                !
              </div>

              <div>
                <div className="text-sm font-medium text-[#7D3636]">
                  We couldn't load everything
                </div>

                <p className="mt-1 text-xs leading-5 text-[#925C5C]">
                  {error}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* ===================================================
            HERO
            =================================================== */}

        <section className="relative overflow-hidden rounded-[28px] border border-[#DFE6E1] bg-white">
          <div className="absolute right-0 top-0 h-48 w-48 rounded-full bg-[#EDF8F1] opacity-70 blur-3xl" />

          <div className="relative px-7 py-9 sm:px-10 sm:py-11">
            <div className="max-w-2xl">
              <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[#7C8881]">
                Your medication workspace
              </div>

              <h1 className="mt-3 text-3xl font-semibold tracking-[-0.045em] sm:text-4xl">
                Good to see you, {firstName}.
              </h1>

              <p className="mt-3 max-w-xl text-sm leading-6 text-[#68746D]">
                Keep your prescriptions and medication information
                organized in one place, with pharmacist review when
                needed.
              </p>
            </div>

            {customer ? (
              <div className="mt-7 flex flex-wrap items-center gap-3">
                <div className="inline-flex items-center gap-2 rounded-xl border border-[#CBE0D3] bg-[#EDF8F1] px-3.5 py-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-[#35664D]" />
                  <span className="text-[11px] font-medium text-[#35664D]">
                    Patient profile active
                  </span>
                </div>

                <div className="rounded-xl border border-[#DFE6E1] bg-[#FAFCFB] px-3.5 py-2 font-mono text-[10px] text-[#68746D]">
                  {customer.customer_code}
                </div>
              </div>
            ) : (
              <div className="mt-7 max-w-2xl rounded-2xl border border-[#E9D9AE] bg-[#FFF7DF] px-5 py-4">
                <div className="text-sm font-medium text-[#7E6325]">
                  Your pharmacy profile is not linked yet
                </div>

                <p className="mt-1.5 text-xs leading-5 text-[#92783A]">
                  Your account is ready. Once a pharmacy associates
                  your profile with your prescription, your medication
                  records will appear here.
                </p>
              </div>
            )}
          </div>
        </section>

        {/* ===================================================
            STATS
            =================================================== */}

        <section className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <CustomerStat
            label="Prescriptions"
            value={prescriptions.length}
            description="Your medication records"
          />

          <CustomerStat
            label="Medicines"
            value={medicationCount}
            description="Unique medicines recorded"
          />

          <CustomerStat
            label="Pharmacies"
            value={pharmacies.length}
            description="Connected pharmacy accounts"
          />

          <CustomerStat
            label="Review needed"
            value={reviewCount}
            description={
              reviewCount > 0
                ? "Pharmacist attention recommended"
                : "No review currently flagged"
            }
            alert={reviewCount > 0}
          />
        </section>

        {/* ===================================================
            UNLINKED STATE
            =================================================== */}

        {!customer && (
          <section className="mt-6 rounded-2xl border border-[#DFE6E1] bg-white p-7">
            <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <div className="text-sm font-semibold">
                  Waiting for your pharmacy
                </div>

                <p className="mt-1.5 max-w-xl text-xs leading-5 text-[#78847D]">
                  Your account does not have a pharmacy-linked patient
                  profile yet. Ask your pharmacy to associate your
                  account with your customer record.
                </p>
              </div>

              <Link
                href="/customer/profile"
                className="inline-flex shrink-0 items-center justify-center rounded-xl border border-[#DCE3DE] bg-white px-4 py-2.5 text-xs font-medium text-[#526158] transition hover:border-[#BBC7BF] hover:bg-[#FAFCFB]"
              >
                View account
              </Link>
            </div>
          </section>
        )}

        {/* ===================================================
            LATEST PRESCRIPTION
            =================================================== */}

        {latestPrescription ? (
          <section className="mt-10">
            <div className="flex items-end justify-between">
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#89938E]">
                  Most recent
                </div>

                <h2 className="mt-2 text-xl font-semibold tracking-[-0.03em]">
                  Latest prescription
                </h2>
              </div>

              <Link
                href="/customer/prescriptions"
                className="hidden text-xs font-medium text-[#526C5D] hover:underline sm:block"
              >
                View all →
              </Link>
            </div>

            <div className="mt-5 overflow-hidden rounded-2xl border border-[#DFE6E1] bg-white">
              <div className="p-6 sm:p-7">
                <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <div className="font-mono text-xs text-[#7C8881]">
                      {getPrescriptionId(latestPrescription)}
                    </div>

                    <div className="mt-2 text-lg font-semibold">
                      Prescription record
                    </div>

                    <div className="mt-1 text-xs text-[#89938E]">
                      {formatDate(latestPrescription.created_at)}
                    </div>
                  </div>

                  {(() => {
                    const status =
                      getPrescriptionStatus(
                        latestPrescription
                      );

                    return (
                      <div
                        className={`inline-flex w-fit items-center gap-2 rounded-full border px-3 py-1.5 text-[10px] font-medium ${statusClasses(
                          status.tone
                        )}`}
                      >
                        <span className="h-1.5 w-1.5 rounded-full bg-current" />
                        {status.label}
                      </div>
                    );
                  })()}
                </div>

                {/* Medicines */}
                <div className="mt-6 border-t border-[#EDF0EE] pt-5">
                  <div className="text-[10px] font-semibold uppercase tracking-[0.15em] text-[#89938E]">
                    Medicines
                  </div>

                  {(latestPrescription.medicines ?? []).length >
                  0 ? (
                    <div className="mt-3 divide-y divide-[#EDF0EE]">
                      {(
                        latestPrescription.medicines ?? []
                      )
                        .slice(0, 3)
                        .map((medicine, index) => (
                          <div
                            key={`${getMedicineName(
                              medicine
                            )}-${index}`}
                            className="flex items-center justify-between gap-4 py-3"
                          >
                            <div className="min-w-0">
                              <div className="truncate text-sm font-medium">
                                {getMedicineName(medicine)}
                              </div>

                              {getMedicineDetails(
                                medicine
                              ) && (
                                <div className="mt-1 text-[11px] text-[#7C8881]">
                                  {getMedicineDetails(
                                    medicine
                                  )}
                                </div>
                              )}
                            </div>

                            <span className="shrink-0 text-[10px] text-[#9AA39E]">
                              Recorded
                            </span>
                          </div>
                        ))}
                    </div>
                  ) : (
                    <div className="mt-3 rounded-xl bg-[#FAFCFB] px-4 py-3 text-xs text-[#7C8881]">
                      Medicine information is not available for
                      this prescription yet.
                    </div>
                  )}
                </div>

                <div className="mt-5 flex flex-col gap-3 border-t border-[#EDF0EE] pt-5 sm:flex-row sm:items-center sm:justify-between">
                  <div className="text-xs text-[#7C8881]">
                    {(() => {
                      const status =
                        getPrescriptionStatus(
                          latestPrescription
                        );

                      return status.description;
                    })()}
                  </div>

                  <Link
                    href={`/customer/prescriptions/${getPrescriptionId(
                      latestPrescription
                    )}`}
                    className="inline-flex items-center justify-center rounded-xl bg-[#17211D] px-4 py-2.5 text-xs font-medium text-white transition hover:bg-[#26332D]"
                  >
                    View prescription →
                  </Link>
                </div>
              </div>
            </div>
          </section>
        ) : (
          /* =================================================
             EMPTY PRESCRIPTION STATE
             ================================================= */

          <section className="mt-10 rounded-2xl border border-dashed border-[#D6DFD9] bg-white px-7 py-12 text-center">
            <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-[#F1F5F2] text-sm font-semibold text-[#65746B]">
              Rx
            </div>

            <h2 className="mt-5 text-base font-semibold">
              No prescriptions yet
            </h2>

            <p className="mx-auto mt-2 max-w-md text-xs leading-5 text-[#8A948F]">
              Your prescriptions will appear here once a pharmacy
              associates them with your patient profile.
            </p>

            <Link
              href="/customer/profile"
              className="mt-6 inline-flex rounded-xl border border-[#DCE3DE] bg-white px-4 py-2.5 text-xs font-medium text-[#526158] transition hover:border-[#BBC7BF]"
            >
              View profile
            </Link>
          </section>
        )}

        {/* ===================================================
            PHARMACY CONNECTIONS
            =================================================== */}

        {pharmacies.length > 0 && (
          <section className="mt-10">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#89938E]">
                Connected care
              </div>

              <h2 className="mt-2 text-xl font-semibold tracking-[-0.03em]">
                Your pharmacies
              </h2>

              <p className="mt-1.5 text-xs text-[#7C8881]">
                Pharmacies currently connected to your medication
                profile.
              </p>
            </div>

            <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {pharmacies.map((pharmacy) => (
                <div
                  key={pharmacy.id}
                  className="rounded-2xl border border-[#DFE6E1] bg-white p-5"
                >
                  <div className="flex items-start gap-4">
                    <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#EDF8F1] text-[#35664D]">
                      +
                    </div>

                    <div className="min-w-0">
                      <div className="truncate text-sm font-semibold">
                        {pharmacy.name}
                      </div>

                      <div className="mt-1 text-[10px] uppercase tracking-[0.12em] text-[#9AA39E]">
                        Connected pharmacy
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* ===================================================
            TRUST / SAFETY
            =================================================== */}

        <section className="mt-10 mb-4 rounded-2xl border border-[#DFE6E1] bg-[#FAFCFB] p-6">
          <div className="flex flex-col gap-5 sm:flex-row sm:items-start">
            <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-[#CBE0D3] bg-[#EDF8F1] text-[#35664D]">
              ✓
            </div>

            <div>
              <div className="text-sm font-semibold">
                Your information is designed for safer medication
                decisions
              </div>

              <p className="mt-1.5 max-w-3xl text-xs leading-5 text-[#77847D]">
                Prescription Intelligence helps organize prescription
                information and identify records that may require
                pharmacist attention. It does not replace your
                pharmacist or doctor.
              </p>

              <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-[10px] font-medium text-[#7C8881]">
                <span>Pharmacist review</span>
                <span>Medication records</span>
                <span>Safety-aware workflow</span>
              </div>
            </div>
          </div>
        </section>
      </section>
    </main>
  );
}

// =========================================================
// Stat component
// =========================================================

function CustomerStat({
  label,
  value,
  description,
  alert = false,
}: {
  label: string;
  value: number;
  description: string;
  alert?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-[#DFE6E1] bg-white p-5">
      <div className="text-[10px] font-semibold uppercase tracking-[0.15em] text-[#89938E]">
        {label}
      </div>

      <div
        className={`mt-3 text-3xl font-semibold tracking-[-0.04em] ${
          alert ? "text-[#A47B2C]" : "text-[#17211D]"
        }`}
      >
        {value}
      </div>

      <div className="mt-1.5 text-[11px] leading-5 text-[#8A948F]">
        {description}
      </div>
    </div>
  );
}