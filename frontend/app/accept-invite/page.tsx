"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

function AcceptInviteContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    const t = searchParams.get("token") || "";
    const e = searchParams.get("email") || "";
    setToken(t);
    setEmail(e);
  }, [searchParams]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");

    if (!password || password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

      const res = await fetch(`${apiUrl}/auth/accept-invite`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, token, password }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        throw new Error(
          typeof data?.detail === "string"
            ? data.detail
            : "Failed to accept invitation"
        );
      }

      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  if (!token || !email) {
    return (
      <main className="min-h-screen bg-[#f4f7f5] px-6 py-12 text-[#17211d]">
        <div className="mx-auto flex min-h-[calc(100vh-6rem)] max-w-md items-center justify-center">
          <div className="w-full rounded-3xl border border-[#dfe6e1] bg-white p-8 text-center">
            <div className="text-3xl font-semibold text-[#cdd6d0]">!</div>
            <h1 className="mt-4 text-lg font-semibold">Invalid invitation link</h1>
            <p className="mt-2 text-sm text-[#77847d]">
              This invitation link is missing required information. Please use the
              link from your invitation email.
            </p>
            <Link
              href="/sign-in"
              className="mt-6 inline-flex rounded-xl bg-[#17211d] px-5 py-2.5 text-sm font-medium text-white hover:bg-[#26332d] transition"
            >
              Sign in
            </Link>
          </div>
        </div>
      </main>
    );
  }

  if (success) {
    return (
      <main className="min-h-screen bg-[#f4f7f5] px-6 py-12 text-[#17211d]">
        <div className="mx-auto flex min-h-[calc(100vh-6rem)] max-w-md items-center justify-center">
          <div className="w-full rounded-3xl border border-[#dfe6e1] bg-white p-8 text-center">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-[#edf8f1] text-[#35664d]">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
                <path d="M20 6 9 17l-5-5" />
              </svg>
            </div>
            <h1 className="mt-5 text-xl font-semibold tracking-[-0.03em]">
              Account activated
            </h1>
            <p className="mt-2 text-sm leading-6 text-[#77847d]">
              Your pharmacy account is ready. Sign in with your email and
              the password you just set.
            </p>
            <button
              type="button"
              onClick={() => router.push("/sign-in")}
              className="mt-6 inline-flex rounded-xl bg-[#17211d] px-6 py-2.5 text-sm font-medium text-white hover:bg-[#26332d] transition"
            >
              Sign in →
            </button>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#f4f7f5] px-6 py-12 text-[#17211d]">
      <div className="mx-auto flex min-h-[calc(100vh-6rem)] max-w-md items-center justify-center">
        <section className="w-full rounded-3xl border border-[#dfe6e1] bg-white p-8 shadow-[0_24px_70px_rgba(23,33,29,0.08)]">

          {/* Brand */}
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#17211d] text-white">
              <span className="text-lg font-semibold">Rx</span>
            </div>
            <div>
              <p className="text-sm font-semibold">Prescription Intelligence</p>
              <p className="text-xs text-[#7c8881]">Pharmacy invitation</p>
            </div>
          </div>

          <div className="mt-8">
            <h1 className="text-2xl font-semibold tracking-[-0.03em]">
              Accept invitation
            </h1>
            <p className="mt-2 text-sm leading-6 text-[#526158]">
              Set a password to activate your pharmacy account
              {email && (
                <>
                  {" "}for <strong className="font-medium text-[#17211d]">{email}</strong>
                </>
              )}.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="mt-7 space-y-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-[#46534c]">
                New password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Minimum 8 characters"
                autoComplete="new-password"
                disabled={loading}
                className="h-11 w-full rounded-xl border border-[#dfe6e1] bg-[#fafcfb] px-4 text-sm outline-none transition focus:border-[#35664d] focus:bg-white disabled:opacity-60"
              />
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-medium text-[#46534c]">
                Confirm password
              </label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Re-enter your password"
                autoComplete="new-password"
                disabled={loading}
                className="h-11 w-full rounded-xl border border-[#dfe6e1] bg-[#fafcfb] px-4 text-sm outline-none transition focus:border-[#35664d] focus:bg-white disabled:opacity-60"
              />
            </div>

            {error && (
              <div className="rounded-xl border border-[#ead8d2] bg-[#fbf5f2] px-4 py-3 text-sm text-[#8b5547]">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-[#17211d] text-sm font-medium text-white transition hover:bg-[#26352e] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? "Activating account…" : "Activate account →"}
            </button>
          </form>

          <p className="mt-6 text-center text-xs text-[#77847d]">
            Already have an account?{" "}
            <Link href="/sign-in" className="font-medium text-[#35664d] hover:underline">
              Sign in
            </Link>
          </p>
        </section>
      </div>
    </main>
  );
}

export default function AcceptInvitePage() {
  return (
    <Suspense fallback={
      <main className="min-h-screen bg-[#f4f7f5] flex items-center justify-center">
        <div className="text-sm text-[#718078]">Loading…</div>
      </main>
    }>
      <AcceptInviteContent />
    </Suspense>
  );
}
