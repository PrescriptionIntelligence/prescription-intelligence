"use client";

import { FormEvent, useState } from "react";
import AppShell from "../../../components/AppShell";
import { authFetch } from "../../../lib/auth";
import Link from "next/link";

export default function InvitePharmacistPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState<{ email: string; sent: boolean } | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setSuccess(null);

    if (!name.trim() || !email.trim()) {
      setError("Please enter a name and email address.");
      return;
    }

    setLoading(true);

    try {
      const res = await authFetch("/users/invite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), email: email.trim() }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        throw new Error(
          typeof data?.detail === "string"
            ? data.detail
            : "Failed to send invitation"
        );
      }

      setSuccess({ email: data.email, sent: data.email_sent });
      setName("");
      setEmail("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send invitation");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell>
      <div className="px-6 py-10 lg:px-10">
        <div className="mx-auto max-w-lg">

          {/* Back */}
          <Link
            href="/settings/organization"
            className="inline-flex items-center gap-1.5 text-xs text-[#77847d] hover:text-[#17211d] mb-6 transition"
          >
            ← Back to settings
          </Link>

          {/* Header */}
          <div className="mb-8">
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#77847d]">
              Team
            </div>
            <h1 className="mt-2 text-2xl font-semibold tracking-[-0.04em]">
              Invite a pharmacist
            </h1>
            <p className="mt-2 text-sm leading-6 text-[#737e78]">
              The invited pharmacist will receive an email to set up their account
              and will be added to your pharmacy workspace.
            </p>
          </div>

          <div className="rounded-2xl border border-[#dfe6e1] bg-white px-6 py-6">
            {success ? (
              <div>
                <div className="rounded-xl border border-[#c8e4d0] bg-[#edf8f1] px-4 py-4">
                  <div className="text-sm font-semibold text-[#35664d]">
                    {success.sent ? "Invitation sent" : "Invitation created"}
                  </div>
                  <p className="mt-1 text-sm text-[#526158]">
                    {success.sent
                      ? `An invitation email has been sent to ${success.email}.`
                      : `The account was created for ${success.email}, but the email could not be sent. Ask them to use "Resend verification".`}
                  </p>
                </div>
                <div className="mt-5 flex gap-3">
                  <button
                    type="button"
                    onClick={() => setSuccess(null)}
                    className="rounded-xl bg-[#17211d] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#26332d]"
                  >
                    Invite another
                  </button>
                  <Link
                    href="/settings/organization"
                    className="rounded-xl border border-[#dfe6e1] px-5 py-2.5 text-sm font-medium text-[#344f42] transition hover:border-[#b8cfc0]"
                  >
                    Back to settings
                  </Link>
                </div>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-5">
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-[#46534c]">
                    Full name
                  </label>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Pharmacist's full name"
                    minLength={2}
                    maxLength={200}
                    disabled={loading}
                    className="h-11 w-full rounded-xl border border-[#dfe6e1] bg-[#fafcfb] px-4 text-sm outline-none transition focus:border-[#35664d] focus:bg-white disabled:opacity-60"
                  />
                </div>

                <div>
                  <label className="mb-1.5 block text-xs font-medium text-[#46534c]">
                    Work email
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="pharmacist@example.com"
                    disabled={loading}
                    className="h-11 w-full rounded-xl border border-[#dfe6e1] bg-[#fafcfb] px-4 text-sm outline-none transition focus:border-[#35664d] focus:bg-white disabled:opacity-60"
                  />
                </div>

                {error && (
                  <div className="rounded-xl border border-[#ead8d2] bg-[#fbf5f2] px-4 py-3 text-sm text-[#8b5547]">
                    {error}
                  </div>
                )}

                <div className="flex items-center gap-3 pt-1">
                  <button
                    type="submit"
                    disabled={loading}
                    className="rounded-xl bg-[#17211d] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#26332d] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {loading ? "Sending invitation…" : "Send invitation"}
                  </button>
                  <Link
                    href="/settings/organization"
                    className="text-sm text-[#77847d] hover:text-[#17211d] transition"
                  >
                    Cancel
                  </Link>
                </div>
              </form>
            )}
          </div>

          {/* Security note */}
          <div className="mt-5 rounded-xl border border-[#dfe6e1] bg-[#fafcfb] px-4 py-3">
            <p className="text-[11px] leading-5 text-[#77847d]">
              The invited pharmacist sets their own password when they accept the invitation.
              Their account will be linked to your pharmacy and subject to the same
              email verification requirements.
            </p>
          </div>

        </div>
      </div>
    </AppShell>
  );
}
