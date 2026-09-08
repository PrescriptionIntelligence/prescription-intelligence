"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!email) return;

    setSent(true);
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
                If an account exists for {email}, password reset instructions
                will be sent there.
              </p>
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
                className="w-full rounded-xl border border-[#d9e1dc] bg-[#fafcfb] px-4 py-3 text-sm outline-none focus:border-[#82988b]"
              />

              <button
                type="submit"
                className="mt-5 w-full rounded-xl bg-[#17211d] py-3.5 text-sm font-medium text-white hover:bg-[#26332d]"
              >
                Send reset instructions →
              </button>
            </form>
          )}

        </div>
      </div>
    </main>
  );
}