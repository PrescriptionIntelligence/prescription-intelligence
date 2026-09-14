"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Building2,
  Loader2,
  Mail,
  ShieldCheck,
} from "lucide-react";
import { register } from "../../../lib/auth";

export default function PharmacySignupPage() {
  const router = useRouter();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pharmacyName, setPharmacyName] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();

    setError("");

    if (
      !name.trim() ||
      !email.trim() ||
      !password ||
      !pharmacyName.trim()
    ) {
      setError("Please complete all required fields.");
      return;
    }

    setLoading(true);

    try {
      const result = await register(
        name.trim(),
        email.trim(),
        password,
        pharmacyName.trim()
      );

      const verificationEmail =
        result.user?.email || email.trim();

      router.push(
        `/verify-email?email=${encodeURIComponent(
          verificationEmail
        )}`
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Registration failed. Please try again."
      );
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#F4F7F5] px-6 py-12 text-[#17211D]">
      <div className="mx-auto flex min-h-[calc(100vh-6rem)] max-w-2xl items-center justify-center">
        <section className="w-full rounded-3xl border border-[#DFE6E1] bg-white p-8 shadow-[0_24px_70px_rgba(23,33,29,0.08)] md:p-10">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#17211D] text-white">
              <span className="text-lg font-semibold">Rx</span>
            </div>

            <div>
              <p className="text-sm font-semibold">
                Prescription Intelligence
              </p>
              <p className="text-xs text-[#7C8881]">
                Pharmacy account
              </p>
            </div>
          </div>

          <div className="mt-10">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#EDF8F1] text-[#35664D]">
              <Building2 className="h-6 w-6" />
            </div>

            <h1 className="mt-5 text-3xl font-semibold tracking-tight">
              Create pharmacy account
            </h1>

            <p className="mt-2 max-w-lg text-sm leading-6 text-[#526158]">
              Set up your pharmacy workspace for prescription
              analysis, medication intelligence and pharmacist
              review.
            </p>
          </div>

          <form
            onSubmit={handleSubmit}
            className="mt-8 space-y-5"
          >
            <div>
              <label className="mb-2 block text-sm font-medium">
                Full name
              </label>

              <input
                value={name}
                onChange={(event) =>
                  setName(event.target.value)
                }
                placeholder="Your full name"
                autoComplete="name"
                className="h-12 w-full rounded-xl border border-[#DFE6E1] bg-[#FAFCFB] px-4 text-sm outline-none transition focus:border-[#35664D] focus:bg-white"
              />
            </div>

            <div>
              <label className="mb-2 block text-sm font-medium">
                Pharmacy name
              </label>

              <input
                value={pharmacyName}
                onChange={(event) =>
                  setPharmacyName(event.target.value)
                }
                placeholder="Your pharmacy or organization"
                autoComplete="organization"
                className="h-12 w-full rounded-xl border border-[#DFE6E1] bg-[#FAFCFB] px-4 text-sm outline-none transition focus:border-[#35664D] focus:bg-white"
              />
            </div>

            <div>
              <label className="mb-2 block text-sm font-medium">
                Work email
              </label>

              <div className="relative">
                <Mail className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#7C8881]" />

                <input
                  type="email"
                  value={email}
                  onChange={(event) =>
                    setEmail(event.target.value)
                  }
                  placeholder="you@pharmacy.com"
                  autoComplete="email"
                  className="h-12 w-full rounded-xl border border-[#DFE6E1] bg-[#FAFCFB] pl-11 pr-4 text-sm outline-none transition focus:border-[#35664D] focus:bg-white"
                />
              </div>

              <p className="mt-2 text-xs text-[#7C8881]">
                A verification email will be sent to confirm
                ownership of this address.
              </p>
            </div>

            <div>
              <label className="mb-2 block text-sm font-medium">
                Password
              </label>

              <input
                type="password"
                value={password}
                onChange={(event) =>
                  setPassword(event.target.value)
                }
                placeholder="Create a secure password"
                autoComplete="new-password"
                className="h-12 w-full rounded-xl border border-[#DFE6E1] bg-[#FAFCFB] px-4 text-sm outline-none transition focus:border-[#35664D] focus:bg-white"
              />
            </div>

            {error && (
              <div className="rounded-xl border border-[#F0CCCC] bg-[#FFF0F0] px-4 py-3 text-sm leading-5 text-[#A74646]">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-[#17211D] text-sm font-medium text-white transition hover:bg-[#26352E] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Creating account...
                </>
              ) : (
                <>
                  Create pharmacy account
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </button>
          </form>

          <div className="mt-7 flex items-start gap-3 rounded-2xl border border-[#DFE6E1] bg-[#FAFCFB] p-4">
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-[#35664D]" />

            <p className="text-xs leading-5 text-[#526158]">
              Email verification is required before this
              account can sign in or access the pharmacy
              workspace.
            </p>
          </div>

          <p className="mt-7 text-center text-sm text-[#7C8881]">
            Already have an account?{" "}
            <button
              type="button"
              onClick={() => router.push("/sign-in")}
              className="font-medium text-[#35664D] hover:underline"
            >
              Sign in
            </button>
          </p>
        </section>
      </div>
    </main>
  );
}