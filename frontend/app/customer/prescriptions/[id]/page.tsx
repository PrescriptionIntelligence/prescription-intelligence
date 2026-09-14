"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  authFetch,
  fetchMe,
  getUser,
  isAuthenticated,
  logout,
  User,
} from "../../../../lib/auth";

// =========================================================
// Types
// =========================================================

type Medicine = {
  id?: string;
  medicine_name?: string | null;
  name?: string | null;
  strength?: string | null;
  dosage?: string | null;
  dose?: string | null;
  frequency?: string | null;
  duration?: string | null;
  instructions?: string | null;
  status?: string | null;
};

type SafetyFlag = {
  type?: string | null;
  severity?: string | null;
  medicine?: string | null;
  message?: string | null;
  recommended_action?: string | null;
  interaction_details?: string | null;
  review_action?: string | null;
};

type Prescription = {
  id?: string;
  prescription_id?: string;
  file_name?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  status?: string | null;
  review_status?: string | null;
  reviewed_at?: string | null;
  review_notes?: string | null;
  medicines?: Medicine[];
  safety_flags?: SafetyFlag[];
  safety_analysis?: {
    safety_flags?: SafetyFlag[];
    findings?: SafetyFlag[];
  } | null;
  analysis?: {
    medicines?: Medicine[];
    safety_flags?: SafetyFlag[];
  } | null;
  report_url?: string | null;
};

type ApiPrescriptionResponse =
  | Prescription
  | {
      prescription?: Prescription;
      data?: Prescription;
    };

// =========================================================
// Helpers
// =========================================================

function getId(value: Prescription): string {
  return value.prescription_id || value.id || "unknown";
}

function getMedicineName(medicine: Medicine): string {
  return medicine.medicine_name || medicine.name || "Medicine";
}

function getMedicineDetails(medicine: Medicine): string {
  return [
    medicine.strength,
    medicine.dosage || medicine.dose,
    medicine.frequency,
  ]
    .filter(Boolean)
    .join(" · ");
}

function formatDate(value?: string | null): string {
  if (!value) return "Date unavailable";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Date unavailable";
  }

  return date.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function formatDateTime(value?: string | null): string {
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

function getReviewStatus(prescription: Prescription) {
  const review = (
    prescription.review_status || ""
  ).toLowerCase();

  const status = (
    prescription.status || ""
  ).toLowerCase();

  if (
    review === "verified" ||
    status === "verified"
  ) {
    return {
      label: "Verified",
      tone: "verified" as const,
      title: "Prescription verified",
      description:
        "This prescription has been reviewed by a pharmacist.",
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
      title: "Pharmacist review recommended",
      description:
        "Some information requires pharmacist attention before dispensing or clinical use.",
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
      title: "Prescription is being processed",
      description:
        "The prescription record is still being prepared.",
    };
  }

  return {
    label: "Available",
    tone: "neutral" as const,
    title: "Prescription available",
    description:
      "Your prescription record is available.",
  };
}

function getStatusClasses(
  tone: "verified" | "review" | "processing" | "neutral"
): string {
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

function getSafetyFlags(
  prescription: Prescription
): SafetyFlag[] {
  if (
    prescription.safety_flags &&
    prescription.safety_flags.length > 0
  ) {
    return prescription.safety_flags;
  }

  if (
    prescription.safety_analysis?.safety_flags &&
    prescription.safety_analysis.safety_flags.length > 0
  ) {
    return prescription.safety_analysis.safety_flags;
  }

  if (
    prescription.safety_analysis?.findings &&
    prescription.safety_analysis.findings.length > 0
  ) {
    return prescription.safety_analysis.findings;
  }

  if (
    prescription.analysis?.safety_flags &&
    prescription.analysis.safety_flags.length > 0
  ) {
    return prescription.analysis.safety_flags;
  }

  return [];
}

function isHighPriority(flag: SafetyFlag): boolean {
  const severity = (
    flag.severity || ""
  ).toLowerCase();

  return (
    severity === "high" ||
    severity === "critical" ||
    severity === "error"
  );
}

function getSafetyTitle(flag: SafetyFlag): string {
  const type = (flag.type || "").toLowerCase();

  if (type === "strength_conflict") {
    return "Strength verification needed";
  }

  if (
    type === "drug_interaction" ||
    type === "interaction"
  ) {
    return "Medication interaction";
  }

  if (type === "ambiguous_medicine") {
    return "Medicine information needs review";
  }

  if (type === "duration_missing") {
    return "Duration not specified";
  }

  return "Safety information";
}

function getSafetyDescription(flag: SafetyFlag): string {
  if (flag.message) {
    return flag.message;
  }

  if (flag.interaction_details) {
    return flag.interaction_details;
  }

  return "Your pharmacist may need to review this information.";
}

// =========================================================
// Page
// =========================================================

export default function CustomerPrescriptionDetailPage() {
  const router = useRouter();
  const params = useParams();

  const prescriptionId = Array.isArray(params.id)
    ? params.id[0]
    : params.id;

  const [user, setUser] = useState<User | null>(null);
  const [prescription, setPrescription] =
    useState<Prescription | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadPrescription() {
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

        if (!prescriptionId) {
          throw new Error(
            "Prescription identifier is missing."
          );
        }

        const response = await authFetch(
          `/prescriptions/${encodeURIComponent(
            prescriptionId
          )}`
        );

        if (!response.ok) {
          if (response.status === 403) {
            throw new Error(
              "You do not have access to this prescription."
            );
          }

          if (response.status === 404) {
            throw new Error(
              "This prescription could not be found."
            );
          }

          throw new Error(
            "Unable to load this prescription."
          );
        }

        const data: ApiPrescriptionResponse =
          await response.json();

        if (cancelled) return;

        let record: Prescription;

        if ("prescription" in data && data.prescription) {
          record = data.prescription;
        } else if ("data" in data && data.data) {
          record = data.data;
        } else {
          record = data as Prescription;
        }

        setPrescription(record);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load this prescription."
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadPrescription();

    return () => {
      cancelled = true;
    };
  }, [prescriptionId, router]);

  const safetyFlags = useMemo(
    () =>
      prescription
        ? getSafetyFlags(prescription)
        : [],
    [prescription]
  );

  const highPriorityFlags = useMemo(
    () => safetyFlags.filter(isHighPriority),
    [safetyFlags]
  );

  const medicines = prescription?.medicines ?? [];

  const reviewStatus = prescription
    ? getReviewStatus(prescription)
    : null;

  // =========================================================
  // Loading
  // =========================================================

  if (loading) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#F4F7F5]">
        <div className="flex items-center gap-3 text-sm text-[#718078]">
          <span className="h-2 w-2 animate-pulse rounded-full bg-[#35664D]" />
          Loading prescription…
        </div>
      </main>
    );
  }

  // =========================================================
  // Error
  // =========================================================

  if (error || !prescription) {
    return (
      <main className="min-h-screen bg-[#F4F7F5] text-[#17211D]">
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

            <button
              onClick={logout}
              className="rounded-xl border border-[#DCE3DE] bg-white px-4 py-2 text-xs font-medium text-[#53625A]"
            >
              Log out
            </button>
          </div>
        </header>

        <section className="mx-auto max-w-xl px-6 py-20 text-center">
          <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-[#FFF0F0] text-sm font-semibold text-[#A74646]">
            !
          </div>

          <h1 className="mt-5 text-xl font-semibold">
            Prescription unavailable
          </h1>

          <p className="mt-2 text-sm leading-6 text-[#7C8881]">
            {error ||
              "We couldn't load this prescription."}
          </p>

          <Link
            href="/customer/prescriptions"
            className="mt-7 inline-flex rounded-xl bg-[#17211D] px-5 py-2.5 text-xs font-medium text-white hover:bg-[#26332D]"
          >
            ← Back to prescriptions
          </Link>
        </section>
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

      {/* =====================================================
          CONTENT
          ===================================================== */}

      <section className="mx-auto max-w-7xl px-6 py-9">
        {/* Breadcrumb */}
        <div className="flex flex-wrap items-center gap-2 text-[10px] text-[#89938E]">
          <Link
            href="/customer"
            className="hover:text-[#526158]"
          >
            Overview
          </Link>

          <span>/</span>

          <Link
            href="/customer/prescriptions"
            className="hover:text-[#526158]"
          >
            Prescriptions
          </Link>

          <span>/</span>

          <span className="font-mono text-[#526158]">
            {getId(prescription)}
          </span>
        </div>

        {/* ===================================================
            TITLE
            =================================================== */}

        <div className="mt-7 flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#89938E]">
              Prescription record
            </div>

            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.045em]">
              Your prescription
            </h1>

            <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-[#7C8881]">
              <span className="font-mono">
                {getId(prescription)}
              </span>

              <span className="h-1 w-1 rounded-full bg-[#B9C3BD]" />

              <span>
                {formatDate(prescription.created_at)}
              </span>
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <Link
              href="/customer/prescriptions"
              className="inline-flex items-center rounded-xl border border-[#DCE3DE] bg-white px-4 py-2.5 text-xs font-medium text-[#526158] transition hover:border-[#BBC7BF]"
            >
              ← All prescriptions
            </Link>

            {prescription.report_url && (
              <a
                href={prescription.report_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center rounded-xl bg-[#17211D] px-4 py-2.5 text-xs font-medium text-white transition hover:bg-[#26332D]"
              >
                View report
              </a>
            )}
          </div>
        </div>

        {/* ===================================================
            REVIEW STATUS
            =================================================== */}

        {reviewStatus && (
          <section className="mt-7">
            <div
              className={`rounded-2xl border p-5 ${getStatusClasses(
                reviewStatus.tone
              )}`}
            >
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
                <div className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white/70">
                  {reviewStatus.tone === "verified"
                    ? "✓"
                    : reviewStatus.tone === "review"
                    ? "!"
                    : "•"}
                </div>

                <div>
                  <div className="flex flex-wrap items-center gap-3">
                    <h2 className="text-sm font-semibold">
                      {reviewStatus.title}
                    </h2>

                    <span className="rounded-full border border-current/15 bg-white/50 px-2.5 py-1 text-[9px] font-semibold uppercase tracking-[0.08em]">
                      {reviewStatus.label}
                    </span>
                  </div>

                  <p className="mt-1.5 max-w-3xl text-xs leading-5 opacity-80">
                    {reviewStatus.description}
                  </p>

                  {prescription.reviewed_at && (
                    <div className="mt-3 text-[10px] opacity-70">
                      Last reviewed{" "}
                      {formatDateTime(
                        prescription.reviewed_at
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </section>
        )}

        {/* ===================================================
            HIGH PRIORITY SAFETY
            =================================================== */}

        {highPriorityFlags.length > 0 && (
          <section className="mt-6">
            <div className="overflow-hidden rounded-2xl border border-[#E5CACA] bg-[#FFF0F0]">
              <div className="border-b border-[#EBCFCF] px-6 py-4">
                <div className="flex items-center gap-2">
                  <span className="grid h-7 w-7 place-items-center rounded-lg bg-[#A74646] text-xs font-bold text-white">
                    !
                  </span>

                  <div>
                    <h2 className="text-sm font-semibold text-[#7D3636]">
                      Important safety information
                    </h2>

                    <p className="mt-0.5 text-[10px] text-[#925C5C]">
                      {highPriorityFlags.length} item
                      {highPriorityFlags.length === 1
                        ? ""
                        : "s"} require
                      pharmacist attention.
                    </p>
                  </div>
                </div>
              </div>

              <div className="divide-y divide-[#EBCFCF]">
                {highPriorityFlags.map(
                  (flag, index) => (
                    <div
                      key={`${flag.type}-${index}`}
                      className="px-6 py-5"
                    >
                      <div className="text-xs font-semibold text-[#7D3636]">
                        {getSafetyTitle(flag)}
                      </div>

                      {flag.medicine && (
                        <div className="mt-1 text-[10px] font-medium text-[#925C5C]">
                          Medicine: {flag.medicine}
                        </div>
                      )}

                      <p className="mt-3 max-w-3xl text-xs leading-5 text-[#855050]">
                        {getSafetyDescription(flag)}
                      </p>

                      {flag.recommended_action && (
                        <div className="mt-4 rounded-xl border border-[#E7CECE] bg-white/60 px-4 py-3">
                          <div className="text-[9px] font-semibold uppercase tracking-[0.13em] text-[#A74646]">
                            Recommended action
                          </div>

                          <p className="mt-1 text-[11px] leading-5 text-[#7D4A4A]">
                            {flag.recommended_action}
                          </p>
                        </div>
                      )}

                      {flag.review_action && (
                        <div className="mt-3 text-[10px] text-[#925C5C]">
                          {flag.review_action}
                        </div>
                      )}
                    </div>
                  )
                )}
              </div>
            </div>
          </section>
        )}

        {/* ===================================================
            MEDICINES
            =================================================== */}

        <section className="mt-8">
          <div className="flex items-end justify-between">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#89938E]">
                Medication list
              </div>

              <h2 className="mt-2 text-xl font-semibold tracking-[-0.03em]">
                Medicines
              </h2>
            </div>

            <div className="text-xs text-[#89938E]">
              {medicines.length}{" "}
              {medicines.length === 1
                ? "medicine"
                : "medicines"}
            </div>
          </div>

          {medicines.length > 0 ? (
            <div className="mt-5 grid gap-4 lg:grid-cols-2">
              {medicines.map((medicine, index) => {
                const details =
                  getMedicineDetails(medicine);

                return (
                  <article
                    key={`${getMedicineName(
                      medicine
                    )}-${index}`}
                    className="rounded-2xl border border-[#DFE6E1] bg-white p-6"
                  >
                    <div className="flex items-start gap-4">
                      <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#F1F5F2] text-xs font-semibold text-[#526158]">
                        Rx
                      </div>

                      <div className="min-w-0">
                        <h3 className="text-base font-semibold">
                          {getMedicineName(medicine)}
                        </h3>

                        {medicine.strength && (
                          <div className="mt-1 text-sm font-medium text-[#35664D]">
                            {medicine.strength}
                          </div>
                        )}
                      </div>
                    </div>

                    {details && (
                      <div className="mt-5 rounded-xl bg-[#FAFCFB] px-4 py-3">
                        <div className="text-[9px] font-semibold uppercase tracking-[0.13em] text-[#89938E]">
                          How it was prescribed
                        </div>

                        <div className="mt-1.5 text-xs text-[#526158]">
                          {details}
                        </div>
                      </div>
                    )}

                    {medicine.duration && (
                      <div className="mt-4 flex items-center justify-between border-t border-[#EDF0EE] pt-4">
                        <span className="text-[10px] text-[#89938E]">
                          Duration
                        </span>

                        <span className="text-xs font-medium text-[#526158]">
                          {medicine.duration}
                        </span>
                      </div>
                    )}

                    {medicine.instructions && (
                      <div className="mt-4 border-t border-[#EDF0EE] pt-4">
                        <div className="text-[9px] font-semibold uppercase tracking-[0.13em] text-[#89938E]">
                          Instructions
                        </div>

                        <p className="mt-1.5 text-xs leading-5 text-[#68746D]">
                          {medicine.instructions}
                        </p>
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="mt-5 rounded-2xl border border-dashed border-[#D6DFD9] bg-white px-6 py-10 text-center text-xs text-[#89938E]">
              Medicine information is not available for this
              prescription.
            </div>
          )}
        </section>

        {/* ===================================================
            SAFETY OVERVIEW
            =================================================== */}

        <section className="mt-8">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#89938E]">
              Safety
            </div>

            <h2 className="mt-2 text-xl font-semibold tracking-[-0.03em]">
              Safety overview
            </h2>
          </div>

          {safetyFlags.length === 0 ? (
            <div className="mt-5 rounded-2xl border border-[#CBE0D3] bg-[#EDF8F1] p-6">
              <div className="flex items-start gap-4">
                <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white/70 text-sm font-semibold text-[#35664D]">
                  ✓
                </div>

                <div>
                  <div className="text-sm font-semibold text-[#35664D]">
                    No safety findings shown
                  </div>

                  <p className="mt-1.5 text-xs leading-5 text-[#527561]">
                    No safety findings are currently attached to
                    this prescription record.
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <div className="mt-5 overflow-hidden rounded-2xl border border-[#DFE6E1] bg-white">
              <div className="divide-y divide-[#EDF0EE]">
                {safetyFlags.map((flag, index) => {
                  const high = isHighPriority(flag);

                  return (
                    <div
                      key={`${flag.type}-${index}`}
                      className="p-5"
                    >
                      <div className="flex items-start gap-4">
                        <div
                          className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg ${
                            high
                              ? "bg-[#FFF0F0] text-[#A74646]"
                              : "bg-[#FFF7DF] text-[#A47B2C]"
                          }`}
                        >
                          {high ? "!" : "•"}
                        </div>

                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <div className="text-xs font-semibold">
                              {getSafetyTitle(flag)}
                            </div>

                            <span
                              className={`rounded-full px-2 py-0.5 text-[9px] font-medium ${
                                high
                                  ? "bg-[#FFF0F0] text-[#A74646]"
                                  : "bg-[#FFF7DF] text-[#A47B2C]"
                              }`}
                            >
                              {high
                                ? "Important"
                                : "Review"}
                            </span>
                          </div>

                          {flag.medicine && (
                            <div className="mt-1 text-[10px] text-[#89938E]">
                              {flag.medicine}
                            </div>
                          )}

                          <p className="mt-2 max-w-3xl text-xs leading-5 text-[#68746D]">
                            {getSafetyDescription(flag)}
                          </p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </section>

        {/* ===================================================
            REVIEW NOTE
            =================================================== */}

        {prescription.review_notes && (
          <section className="mt-8">
            <div className="rounded-2xl border border-[#DFE6E1] bg-white p-6">
              <div className="text-[10px] font-semibold uppercase tracking-[0.15em] text-[#89938E]">
                Pharmacist note
              </div>

              <p className="mt-3 text-sm leading-6 text-[#526158]">
                {prescription.review_notes}
              </p>
            </div>
          </section>
        )}

        {/* ===================================================
            FOOTER NOTICE
            =================================================== */}

        <section className="mt-8 mb-5 rounded-2xl border border-[#DFE6E1] bg-[#FAFCFB] p-6">
          <div className="flex items-start gap-4">
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-[#D8E1DB] bg-white text-xs font-semibold text-[#526158]">
              i
            </div>

            <div>
              <div className="text-xs font-semibold text-[#526158]">
                Important
              </div>

              <p className="mt-1.5 max-w-3xl text-[11px] leading-5 text-[#7C8881]">
                Prescription Intelligence provides medication
                information and safety decision support. It does not
                replace advice from your doctor or pharmacist. Always
                follow the instructions on your original prescription
                and ask a qualified healthcare professional if you
                have questions.
              </p>
            </div>
          </div>
        </section>
      </section>
    </main>
  );
}