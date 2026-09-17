"use client";

import Link from "next/link";
import { FormEvent, Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { resetPassword } from "../../lib/auth";

type PageState =
  | "form"
  | "loading"
  | "success"
  | "invalid"
  | "expired"
  | "error";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [token, setToken] = useState<string>("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [state, setState] = useState<PageState>("form");
  const [error, setError] = useState("");

  useEffect(() => {
    const t = searchParams.get("token") ?? "";
    if (!t) {
      setState("invalid");
    } else {
      setToken(t);
    }
  }, [searchParams]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (!password || password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }

    setState("loading");

    try {
      await resetPassword(token, password);
      setState("success");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Password reset failed.";

      if (
        message.toLowerCase().includes("expired")
      ) {
        setState("expired");
      } else if (
        message.toLowerCase().includes("invalid") ||
        message.toLowerCase().includes("already been used")
      ) {
        setState("invalid");
      } else {
        setError(message);
        setState("form");
      }
    }
  }

  // -------------------------------------------------------
  // Success
  // -------------------------------------------------------

  if (state === "success") {
    return (
      <div className="mt-8 rounded-2xl border border-[#d9e5dd] bg-[#f3f8f4] p-5">
        <div className="text-sm font-semibold text-[#17211d]">
          Password reset successfully
        </div>

        <p className="mt-2 text-xs leading-5 text-[#718078]">
          Your password has been updated. You can now sign in with
          your new password.
        </p>

        <button
          onClick={() => router.push("/sign-in")}
          className="mt-4 w-full rounded-xl bg-[#17211d] py-3.5 text-sm font-medium text-white transition hover:bg-[#26332d]"
        >
          Sign in →
        </button>
      </div>
    );
  }

  // -------------------------------------------------------
  // Expired token
  // -------------------------------------------------------

  if (state === "expired") {
    return (
      <div className="mt-8 rounded-2xl border border-[#ead8d2] bg-[#fbf5f2] p-5">
        <div className="text-sm font-semibold text-[#8b5547]">
          Link expired
        </div>

        <p className="mt-2 text-xs leading-5 text-[#a06055]">
          This password reset link has expired. Reset links are valid
          for 30 minutes.
        </p>

        <Link
          href="/forgot-password"
          className="mt-4 inline-block text-xs text-[#35664d] hover:text-[#17211d]"
        >
          Request a new reset link →
        </Link>
      </div>
    );
  }

  // -------------------------------------------------------
  // Invalid / already-used token
  // -------------------------------------------------------

  if (state === "invalid") {
    return (
      <div className="mt-8 rounded-2xl border border-[#ead8d2] bg-[#fbf5f2] p-5">
        <div className="text-sm font-semibold text-[#8b5547]">
          Invalid reset link
        </div>

        <p className="mt-2 text-xs leading-5 text-[#a06055]">
          This password reset link is invalid or has already been
          used. Please request a new one.
        </p>

        <Link
          href="/forgot-password"
          className="mt-4 inline-block text-xs text-[#35664d] hover:text-[#17211d]"
        >
          Request a new reset link →
        </Link>
      </div>
    );
  }

  // -------------------------------------------------------
  // Password form
  // -------------------------------------------------------

  const isLoading = state === "loading";

  return (
    <form onSubmit={handleSubmit} className="mt-8 space-y-5">

      <div>
        <label className="mb-2 block text-xs font-medium text-[#46534c]">
          New password
        </label>

        <div className="relative">
          <input
            type={showPassword ? "text" : "password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 8 characters"
            autoComplete="new-password"
            disabled={isLoading}
            className="w-full rounded-xl border border-[#d9e1dc] bg-[#fafcfb] px-4 py-3 pr-20 text-sm outline-none transition placeholder:text-[#a1aaa5] focus:border-[#82988b] focus:ring-2 focus:ring-[#e5ece7] disabled:opacity-60"
          />

          <button
            type="button"
            onClick={() => setShowPassword((v) => !v)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-[#718078] hover:text-[#17211d]"
          >
            {showPassword ? "Hide" : "Show"}
          </button>
        </div>
      </div>

      <div>
        <label className="mb-2 block text-xs font-medium text-[#46534c]">
          Confirm new password
        </label>

        <div className="relative">
          <input
            type={showConfirm ? "text" : "password"}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Repeat your new password"
            autoComplete="new-password"
            disabled={isLoading}
            className="w-full rounded-xl border border-[#d9e1dc] bg-[#fafcfb] px-4 py-3 pr-20 text-sm outline-none transition placeholder:text-[#a1aaa5] focus:border-[#82988b] focus:ring-2 focus:ring-[#e5ece7] disabled:opacity-60"
          />

          <button
            type="button"
            onClick={() => setShowConfirm((v) => !v)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-[#718078] hover:text-[#17211d]"
          >
            {showConfirm ? "Hide" : "Show"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-[#ead8d2] bg-[#fbf5f2] px-4 py-3 text-xs leading-5 text-[#8b5547]">
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={isLoading}
        className="w-full rounded-xl bg-[#17211d] py-3.5 text-sm font-medium text-white transition hover:bg-[#26332d] disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isLoading ? "Resetting…" : "Reset password →"}
      </button>
    </form>
  );
}

export default function ResetPasswordPage() {
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
              Set a new password
            </h1>

            <p className="mt-3 text-sm leading-6 text-[#7b8580]">
              Choose a strong password for your account.
            </p>
          </div>

          <Suspense
            fallback={
              <div className="mt-8 text-sm text-[#7b8580]">
                Loading…
              </div>
            }
          >
            <ResetPasswordForm />
          </Suspense>

        </div>
      </div>
    </main>
  );
}
