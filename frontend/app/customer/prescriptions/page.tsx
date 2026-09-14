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
} from "../../../lib/auth";

type Medicine = {
  id?: string;
  medicine_name?: string | null;
  name?: string | null;
  strength?: string | null;
  dosage?: string | null;
  dose?: string | null;
  frequency?: string | null;
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

type PrescriptionResponse = {
  prescriptions?: Prescription[];
  total?: number;
  skip?: number;
  limit?: number;
};

function prescriptionId(prescription: Prescription): string {
  return prescription.prescription_id || prescription.id || "unknown";
}

function medicineName(medicine: Medicine): string {
  return medicine.medicine_name || medicine.name || "Medicine";
}

function medicineDetails(medicine: Medicine): string {
  return [
    medicine.strength,
    medicine.dosage || medicine.dose,
    medicine.frequency,
  ]
    .filter(Boolean)
    .join(" · ");
}

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

function getStatus(prescription: Prescription) {
  const review = (prescription.review_status || "").toLowerCase();
  const status = (prescription.status || "").toLowerCase();

  if (review === "verified" || status === "verified") {
    return {
      label: "Verified",
      tone: "verified" as const,
      description: "Reviewed by a pharmacist",
    };
  }

  if (
    review === "under_review" ||
    review === "needs_clarification" ||
    review === "pending" ||
    status === "needs_review"
  ) {
    return {
      label: "Review required",
      tone: "review" as const,
      description: "Pharmacist verification recommended",
    };
  }

  if (
    status === "uploaded" ||
    status === "processing" ||
    status === "analyzing"
  ) {
    return {
      label: "Processing",
      tone: "processing" as const,
      description: "Prescription is being processed",
    };
  }

  return {
    label: "Available",
    tone: "neutral" as const,
    description: "Prescription record available",
  };
}

function statusClass(
  tone: "verified" | "review" | "processing" | "neutral"
) {
  switch (tone) {
    case "verified":
      return "border-[#CBE0D3] bg-[#EDF8F1] text-[#35664D]";

    case "review":
      return "border-[#E9D9AE] bg-[#FFF7DF] text-[#A47B2C]";

    case "processing":
      return "border-[#DFE6E1] bg-[#F3F7F5] text-[#526158]";

    default:
      return "border-[#DFE6E1] bg-[#FAFCFB] text-[#526158]";
  }
}

export default function CustomerPrescriptionsPage() {
  const router = useRouter();

  const [user, setUser] = useState<User | null>(null);
  const [prescriptions, setPrescriptions] = useState<
    Prescription[]
  >([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
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

        const response = await authFetch(
          "/customers/me/prescriptions?skip=0&limit=100"
        );

        if (!response.ok) {
          throw new Error(
            "Unable to load your prescriptions."
          );
        }

        const data: PrescriptionResponse =
          await response.json();

        if (cancelled) return;

        setPrescriptions(
          data.prescriptions ??
            (Array.isArray(data) ? data : [])
        );
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load your prescriptions."
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, [router]);

  const totalMedicines = useMemo(() => {
    return prescriptions.reduce(
      (total, prescription) =>
        total + (prescription.medicines?.length || 0),
      0
    );
  }, [prescriptions]);

  if (loading) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#F4F7F5]">
        <div className="flex items-center gap-3 text-sm text-[#718078]">
          <span className="h-2 w-2 animate-pulse rounded-full bg-[#35664D]" />
          Loading prescriptions…
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#F4F7F5] text-[#17211D]">
      {/* Header */}
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
              className="text-xs text-[#637069] hover:text-[#17211D]"
            >
              Overview
            </Link>

            <Link
              href="/customer/prescriptions"
              className="text-xs font-medium text-[#17211D]"
            >
              Prescriptions
            </Link>

            <Link
              href="/customer/profile"
              className="text-xs text-[#637069] hover:text-[#17211D]"
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
              className="rounded-xl border border-[#DCE3DE] bg-white px-4 py-2 text-xs font-medium text-[#53625A] transition hover:border-[#BBC7BF]"
            >
              Log out
            </button>
          </div>
        </div>
      </header>

      {/* Content */}
      <section className="mx-auto max-w-7xl px-6 py-10">
        {/* Breadcrumb */}
        <div className="flex items-center gap-2 text-[10px] text-[#89938E]">
          <Link
            href="/customer"
            className="hover:text-[#526158]"
          >
            Overview
          </Link>
          <span>/</span>
          <span className="text-[#526158]">
            Prescriptions
          </span>
        </div>

        {/* Heading */}
        <div className="mt-7 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#89938E]">
              Medication records
            </div>

            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.045em]">
              Your prescriptions
            </h1>

            <p className="mt-2 max-w-xl text-sm leading-6 text-[#737E78]">
              A clear history of prescriptions associated with your
              patient profile.
            </p>
          </div>

          <Link
            href="/customer"
            className="inline-flex w-fit rounded-xl border border-[#DCE3DE] bg-white px-4 py-2.5 text-xs font-medium text-[#526158] hover:border-[#BBC7BF]"
          >
            ← Back to overview
          </Link>
        </div>

        {/* Error */}
        {error && (
          <div className="mt-7 rounded-2xl border border-[#E8D2D2] bg-[#FFF5F5] px-5 py-4 text-xs text-[#925C5C]">
            {error}
          </div>
        )}

        {/* Summary */}
        <div className="mt-8 grid gap-4 sm:grid-cols-3">
          <SummaryCard
            label="Prescriptions"
            value={prescriptions.length}
            description="Records associated with you"
          />

          <SummaryCard
            label="Medicines"
            value={totalMedicines}
            description="Medicine entries across records"
          />

          <SummaryCard
            label="Latest record"
            value={
              prescriptions.length > 0
                ? formatDate(prescriptions[0].created_at)
                : "—"
            }
            description="Most recently added prescription"
            date
          />
        </div>

        {/* Empty */}
        {prescriptions.length === 0 ? (
          <section className="mt-8 rounded-2xl border border-dashed border-[#D6DFD9] bg-white px-7 py-14 text-center">
            <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-[#F1F5F2] text-sm font-semibold text-[#65746B]">
              Rx
            </div>

            <h2 className="mt-5 text-base font-semibold">
              No prescriptions yet
            </h2>

            <p className="mx-auto mt-2 max-w-md text-xs leading-5 text-[#8A948F]">
              Prescriptions associated with your patient profile
              will appear here.
            </p>

            <Link
              href="/customer"
              className="mt-6 inline-flex rounded-xl bg-[#17211D] px-5 py-2.5 text-xs font-medium text-white hover:bg-[#26332D]"
            >
              Return to overview
            </Link>
          </section>
        ) : (
          /* Prescription list */
          <section className="mt-8">
            <div className="space-y-4">
              {prescriptions.map((prescription) => {
                const id = prescriptionId(prescription);
                const status = getStatus(prescription);
                const medicines =
                  prescription.medicines || [];

                return (
                  <article
                    key={id}
                    className="overflow-hidden rounded-2xl border border-[#DFE6E1] bg-white transition hover:border-[#CBD5CF] hover:shadow-sm"
                  >
                    <div className="p-6 sm:p-7">
                      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                        <div>
                          <div className="font-mono text-[11px] text-[#89938E]">
                            {id}
                          </div>

                          <h2 className="mt-2 text-base font-semibold">
                            Prescription record
                          </h2>

                          <div className="mt-1 text-xs text-[#89938E]">
                            {formatDate(
                              prescription.created_at
                            )}
                          </div>
                        </div>

                        <div className="flex flex-wrap items-center gap-3">
                          <div
                            className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[10px] font-medium ${statusClass(
                              status.tone
                            )}`}
                          >
                            <span className="h-1.5 w-1.5 rounded-full bg-current" />
                            {status.label}
                          </div>

                          <Link
                            href={`/customer/prescriptions/${id}`}
                            className="inline-flex items-center rounded-xl bg-[#17211D] px-4 py-2 text-xs font-medium text-white transition hover:bg-[#26332D]"
                          >
                            View →
                          </Link>
                        </div>
                      </div>

                      {/* Medicines */}
                      <div className="mt-6 border-t border-[#EDF0EE] pt-5">
                        <div className="text-[10px] font-semibold uppercase tracking-[0.15em] text-[#89938E]">
                          Medicines
                        </div>

                        {medicines.length > 0 ? (
                          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                            {medicines
                              .slice(0, 3)
                              .map((medicine, index) => (
                                <div
                                  key={`${id}-${index}`}
                                  className="rounded-xl border border-[#E6ECE8] bg-[#FAFCFB] px-4 py-3"
                                >
                                  <div className="text-xs font-medium">
                                    {medicineName(medicine)}
                                  </div>

                                  {medicineDetails(
                                    medicine
                                  ) && (
                                    <div className="mt-1.5 text-[10px] leading-4 text-[#7C8881]">
                                      {medicineDetails(
                                        medicine
                                      )}
                                    </div>
                                  )}
                                </div>
                              ))}
                          </div>
                        ) : (
                          <div className="mt-3 text-xs text-[#89938E]">
                            Medicine information is not available
                            yet.
                          </div>
                        )}

                        {medicines.length > 3 && (
                          <div className="mt-3 text-[10px] text-[#89938E]">
                            + {medicines.length - 3} more medicine
                            {medicines.length - 3 === 1
                              ? ""
                              : "s"}
                          </div>
                        )}
                      </div>

                      {/* Footer */}
                      <div className="mt-5 flex flex-col gap-2 border-t border-[#EDF0EE] pt-4 text-[10px] text-[#89938E] sm:flex-row sm:items-center sm:justify-between">
                        <span>{status.description}</span>

                        {prescription.file_name && (
                          <span className="truncate sm:max-w-xs">
                            Source: {prescription.file_name}
                          </span>
                        )}
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        )}
      </section>
    </main>
  );
}

function SummaryCard({
  label,
  value,
  description,
  date = false,
}: {
  label: string;
  value: number | string;
  description: string;
  date?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-[#DFE6E1] bg-white p-5">
      <div className="text-[10px] font-semibold uppercase tracking-[0.15em] text-[#89938E]">
        {label}
      </div>

      <div
        className={`mt-3 font-semibold tracking-[-0.035em] ${
          date ? "text-xl" : "text-3xl"
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