"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { login, getRoleHome } from "../../../lib/auth";

export default function AdminLoginPage() {
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (!email.trim() || !password) {
      setError("Please enter your administrator credentials.");
      return;
    }

    setLoading(true);

    try {
      const result = await login(email.trim(), password);

      if (result.user.role !== "admin") {
        setError(
          "This account is not authorized for administrator access."
        );
        return;
      }

      router.push(getRoleHome(result.user));
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Admin sign in failed. Please check your credentials."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#f4f7f5] text-[#17211d]">
      <div className="mx-auto flex min-h-screen max-w-6xl items-center justify-center px-6 py-10">
        <div className="w-full max-w-md">

          <div className="mb-8 flex items-center justify-between">
            <Link
              href="/sign-in"
              className="text-xs text-[#718078] hover:text-[#17211d]"
            >
              ← Standard sign in
            </Link>

            <Link href="/" className="flex items-center gap-2">
              <span className="grid h-9 w-9 place-items-center rounded-xl bg-[#17211d] text-xs font-semibold text-white">
                Rx
              </span>

              <span className="hidden text-sm font-semibold sm:block">
                Prescription Intelligence
              </span>
            </Link>
          </div>

          <div className="rounded-[28px] border border-[#dfe6e1] bg-white p-7 shadow-[0_25px_70px_rgba(30,45,38,0.07)] sm:p-9">

            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-[#eadfbd] bg-[#fff7df] px-3 py-1.5 text-[11px] font-medium text-[#8a6925]">
                <span className="h-1.5 w-1.5 rounded-full bg-[#a47b2c]" />
                Authorized access
              </div>

              <h1 className="mt-5 text-3xl font-semibold tracking-[-0.04em]">
                Administrator sign in
              </h1>

              <p className="mt-2 text-sm leading-6 text-[#7b8580]">
                Access is restricted to provisioned administrator accounts.
              </p>
            </div>

            <form onSubmit={handleSubmit} className="mt-8 space-y-5">

              <div>
                <label className="mb-2 block text-xs font-medium text-[#46534c]">
                  Administrator email
                </label>

                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="admin@example.com"
                  autoComplete="username"
                  disabled={loading}
                  className="w-full rounded-xl border border-[#d9e1dc] bg-[#fafcfb] px-4 py-3 text-sm outline-none transition placeholder:text-[#a1aaa5] focus:border-[#82988b] focus:ring-2 focus:ring-[#e5ece7] disabled:opacity-60"
                />
              </div>

              <div>
                <label className="mb-2 block text-xs font-medium text-[#46534c]">
                  Password
                </label>

                <div className="relative">
                  <input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    autoComplete="current-password"
                    disabled={loading}
                    className="w-full rounded-xl border border-[#d9e1dc] bg-[#fafcfb] px-4 py-3 pr-20 text-sm outline-none transition placeholder:text-[#a1aaa5] focus:border-[#82988b] focus:ring-2 focus:ring-[#e5ece7] disabled:opacity-60"
                  />

                  <button
                    type="button"
                    onClick={() => setShowPassword((value) => !value)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-[#718078] hover:text-[#17211d]"
                  >
                    {showPassword ? "Hide" : "Show"}
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
                disabled={loading}
                className="w-full rounded-xl bg-[#17211d] py-3.5 text-sm font-medium text-white transition hover:bg-[#26332d] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {loading ? "Authenticating…" : "Admin sign in →"}
              </button>
            </form>

            <div className="mt-7 border-t border-[#edf0ee] pt-5">
              <p className="text-center text-[11px] leading-5 text-[#89948e]">
                Administrator accounts are created through controlled
                provisioning. Public registration is disabled.
              </p>
            </div>
          </div>

          <p className="mt-6 text-center text-[11px] leading-5 text-[#929b96]">
            Prescription Intelligence administrative access is restricted to
            authorized personnel.
          </p>
        </div>
      </div>
    </main>
  );
}