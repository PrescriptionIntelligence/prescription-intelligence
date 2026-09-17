"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { forgotPassword } from "../../lib/auth";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    const trimmed = email.trim();

    if (!trimmed) {
      setError("Please enter your email address.");
      return;
    }

    setLoading(true);

    try {
      await forgotPassword(trimmed);
      setSent(true);
    } catch {
      // Show the success state even on network/server errors
      // to avoid leaking whether the account exists.
      setSent(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#f3f6f3] px-6 py-10 text-[#17211d]">
      <div className="mx-auto flex min-h-[90vh] max-w-md items-center">

        <div className="w-full rounded-[28px] border border-[#dfe6e1] bg-white p-8 shadow-[0_25px_70px_rgba(30,45,38,0.07)]">

          <Link
            href="/sign-in"
            className="text-xs text-[#68766e] hover:text-[#17211d]"
          >
            ← Back to sign in
          </Link>

          <div className="mt-10">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#77847d]">
              Account recovery
            </div>

            <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em]">
              Reset your password
            </h1>

            <p className="mt-3 text-sm leading-6 text-[#7b8580]">
              Enter your email and we&apos;ll send instructions to reset your
              password.
            </p>
          </div>

          {sent ? (
            <div className="mt-8 rounded-2xl border border-[#d9e5dd] bg-[#f3f8f4] p-5">
              <div className="text-sm font-semibold">
                Check your email
              </div>

              <p className="mt-2 text-xs leading-5 text-[#718078]">
                If an account exists for {email.trim()}, password reset
                instructions will be sent there. The link expires in 30
                minutes.
              </p>

              <Link
                href="/sign-in"
                className="mt-4 inline-block text-xs text-[#35664d] hover:text-[#17211d]"
              >
                ← Return to sign in
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="mt-8">
              <label className="mb-2 block text-xs font-medium text-[#46534c]">
                Email address
              </label>

              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
                disabled={loading}
                className="w-full rounded-xl border border-[#d9e1dc] bg-[#fafcfb] px-4 py-3 text-sm outline-none transition placeholder:text-[#a1aaa5] focus:border-[#82988b] focus:ring-2 focus:ring-[#e5ece7] disabled:opacity-60"
              />

              {error && (
                <div className="mt-3 rounded-xl border border-[#ead8d2] bg-[#fbf5f2] px-4 py-3 text-xs leading-5 text-[#8b5547]">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="mt-5 w-full rounded-xl bg-[#17211d] py-3.5 text-sm font-medium text-white transition hover:bg-[#26332d] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {loading ? "Sending…" : "Send reset instructions →"}
              </button>
            </form>
          )}

        </div>
      </div>
    </main>
  );
}
