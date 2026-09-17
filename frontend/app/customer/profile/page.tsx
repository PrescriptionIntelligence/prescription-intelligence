"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  authFetch,
  fetchMe,
  getUser,
  isAuthenticated,
  logout,
  User,
} from "../../../lib/auth";

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

type CustomerResponse = {
  profile_linked?: boolean;
  customer?: CustomerProfile | null;
  pharmacies?: Pharmacy[];
};

// =========================================================
// Component
// =========================================================

export default function CustomerProfilePage() {
  const router = useRouter();

  const [user, setUser] = useState<User | null>(null);
  const [customer, setCustomer] = useState<CustomerProfile | null>(null);
  const [pharmacies, setPharmacies] = useState<Pharmacy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!isAuthenticated()) {
        router.replace("/sign-in");
        return;
      }

      const stored = getUser();
      if (!stored) {
        router.replace("/sign-in");
        return;
      }
      if (stored.role !== "customer") {
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

        const response = await authFetch("/customers/me");
        if (cancelled) return;

        if (!response.ok) {
          throw new Error("Unable to load your profile.");
        }

        const data: CustomerResponse = await response.json();
        if (cancelled) return;

        setCustomer(data.customer ?? null);
        setPharmacies(data.pharmacies ?? []);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Something went wrong while loading your profile."
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [router]);

  // =========================================================
  // Loading
  // =========================================================

  if (loading) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#F4F7F5]">
        <div className="flex items-center gap-3 text-sm text-[#718078]">
          <span className="h-2 w-2 animate-pulse rounded-full bg-[#35664D]" />
          Loading profile…
        </div>
      </main>
    );
  }

  // =========================================================
  // Error
  // =========================================================

  if (error) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#F4F7F5]">
        <div className="w-full max-w-md rounded-2xl border border-[#E1E7E3] bg-white p-8 text-center">
          <div className="mx-auto grid h-11 w-11 place-items-center rounded-full bg-[#FFF0F0] text-sm text-[#8B4040]">
            !
          </div>
          <h1 className="mt-4 text-base font-semibold text-[#17211D]">
            Unable to load profile
          </h1>
          <p className="mt-2 text-sm leading-6 text-[#7C8882]">{error}</p>
          <Link
            href="/customer"
            className="mt-6 inline-flex rounded-xl bg-[#17211D] px-4 py-2.5 text-xs font-medium text-white transition hover:bg-[#26332D]"
          >
            ← Back to overview
          </Link>
        </div>
      </main>
    );
  }

  // =========================================================
  // Main
  // =========================================================

  return (
    <main className="min-h-screen bg-[#F4F7F5] text-[#17211D]">
      {/* Header */}
      <header className="border-b border-[#DFE6E1] bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <Link href="/customer" className="flex items-center gap-3">
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
              className="text-xs text-[#637069] transition hover:text-[#17211D]"
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
              className="text-xs font-medium text-[#17211D]"
            >
              Profile
            </Link>
          </nav>

          <div className="flex items-center gap-4">
            <div className="hidden text-right sm:block">
              <div className="text-xs font-medium">{user?.name}</div>
              <div className="text-[10px] text-[#8A948F]">Patient account</div>
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

      {/* Content */}
      <section className="mx-auto max-w-3xl px-6 py-10">
        {/* Breadcrumb */}
        <div className="mb-7 flex items-center gap-2 text-[10px] text-[#89938E]">
          <Link href="/customer" className="hover:text-[#526158]">
            Overview
          </Link>
          <span>/</span>
          <span className="text-[#526158]">Profile</span>
        </div>

        <h1 className="text-2xl font-semibold tracking-[-0.04em]">
          Your profile
        </h1>
        <p className="mt-1.5 text-sm text-[#7C8881]">
          Account and linked pharmacy information.
        </p>

        <div className="mt-8 space-y-5">
          {/* Account details */}
          <section className="rounded-2xl border border-[#DFE6E1] bg-white p-6">
            <p className="mb-4 text-xs font-semibold uppercase tracking-[0.14em] text-[#89938E]">
              Account
            </p>
            <div className="divide-y divide-[#EDF0EE]">
              <ProfileRow label="Name" value={user?.name} />
              <ProfileRow label="Email" value={user?.email} />
              <ProfileRow
                label="Account type"
                value="Patient account"
              />
            </div>
          </section>

          {/* Customer profile */}
          {customer ? (
            <section className="rounded-2xl border border-[#DFE6E1] bg-white p-6">
              <p className="mb-4 text-xs font-semibold uppercase tracking-[0.14em] text-[#89938E]">
                Patient profile
              </p>
              <div className="divide-y divide-[#EDF0EE]">
                <ProfileRow label="Patient name" value={customer.name} />
                <ProfileRow label="Customer code" value={customer.customer_code} mono />
                {customer.phone && (
                  <ProfileRow label="Phone" value={customer.phone} />
                )}
                {customer.email && (
                  <ProfileRow label="Patient email" value={customer.email} />
                )}
              </div>
            </section>
          ) : (
            <section className="rounded-2xl border border-[#E9D9AE] bg-[#FFF7DF] p-6">
              <div className="text-sm font-medium text-[#7E6325]">
                No pharmacy profile linked
              </div>
              <p className="mt-1.5 text-xs leading-5 text-[#92783A]">
                Your account is ready. Once a pharmacy associates your profile
                with your prescription records, your patient information will
                appear here.
              </p>
            </section>
          )}

          {/* Connected pharmacies */}
          <section className="rounded-2xl border border-[#DFE6E1] bg-white p-6">
            <p className="mb-4 text-xs font-semibold uppercase tracking-[0.14em] text-[#89938E]">
              Connected pharmacies
            </p>
            {pharmacies.length > 0 ? (
              <ul className="divide-y divide-[#EDF0EE]">
                {pharmacies.map((pharmacy) => (
                  <li key={pharmacy.id} className="flex items-center gap-3 py-3">
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[#EDF8F1] text-xs font-semibold text-[#35664D]">
                      +
                    </span>
                    <span className="text-sm font-medium text-[#17211D]">
                      {pharmacy.name}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-[#89938E]">
                No pharmacies connected to your account yet.
              </p>
            )}
          </section>

          {/* Actions */}
          <section className="rounded-2xl border border-[#DFE6E1] bg-white p-6">
            <p className="mb-4 text-xs font-semibold uppercase tracking-[0.14em] text-[#89938E]">
              Account actions
            </p>
            <button
              onClick={logout}
              className="rounded-xl border border-[#E1E7E3] bg-white px-4 py-2.5 text-xs font-medium text-[#8B5547] transition hover:border-[#DBCACA] hover:bg-[#FBF5F2]"
            >
              Sign out of your account
            </button>
          </section>
        </div>
      </section>
    </main>
  );
}

// =========================================================
// Row helper
// =========================================================

function ProfileRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value?: string | null;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <span className="text-xs font-medium text-[#7B8580]">{label}</span>
      <span
        className={`text-right text-xs text-[#17211D] ${
          mono ? "font-mono" : ""
        }`}
      >
        {value || "—"}
      </span>
    </div>
  );
}
