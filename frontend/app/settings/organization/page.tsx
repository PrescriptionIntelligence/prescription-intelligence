"use client";

import { FormEvent, useEffect, useState } from "react";
import AppShell from "../../../components/AppShell";
import { authFetch, isAuthenticated, getUser } from "../../../lib/auth";
import { useRouter } from "next/navigation";

type OrgProfile = {
  id: string;
  name: string;
  slug: string;
  phone: string | null;
  email: string | null;
  address: string | null;
  is_active: boolean;
  created_at: string;
};

export default function OrganizationSettingsPage() {
  const router = useRouter();

  const [profile, setProfile] = useState<OrgProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // Editable fields
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [address, setAddress] = useState("");

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/sign-in");
      return;
    }
    const user = getUser();
    if (!user || user.role !== "pharmacist") {
      router.replace("/dashboard");
      return;
    }

    authFetch("/users/organization")
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load organization profile");
        return res.json();
      })
      .then((data: OrgProfile) => {
        setProfile(data);
        setName(data.name || "");
        setPhone(data.phone || "");
        setEmail(data.email || "");
        setAddress(data.address || "");
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Could not load profile");
      })
      .finally(() => setLoading(false));
  }, [router]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSaved(false);
    setError("");

    try {
      const res = await authFetch("/users/organization", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim() || undefined,
          phone: phone.trim() || null,
          email: email.trim() || null,
          address: address.trim() || null,
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(
          typeof data?.detail === "string"
            ? data.detail
            : "Failed to save changes"
        );
      }

      const updated: OrgProfile = await res.json();
      setProfile(updated);
      setName(updated.name || "");
      setPhone(updated.phone || "");
      setEmail(updated.email || "");
      setAddress(updated.address || "");
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell>
      <div className="px-6 py-10 lg:px-10">
        <div className="mx-auto max-w-2xl">

          {/* Header */}
          <div className="mb-8">
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#77847d]">
              Settings
            </div>
            <h1 className="mt-2 text-2xl font-semibold tracking-[-0.04em]">
              Organization profile
            </h1>
            <p className="mt-2 text-sm leading-6 text-[#737e78]">
              Update your pharmacy&apos;s contact details and profile information.
            </p>
          </div>

          {loading && (
            <div className="rounded-2xl border border-[#dfe6e1] bg-white p-8 text-center">
              <div className="text-sm text-[#77847d]">Loading profile…</div>
            </div>
          )}

          {!loading && error && (
            <div className="rounded-xl border border-[#ead8d2] bg-[#fbf5f2] px-4 py-3 text-sm text-[#8b5547]">
              {error}
            </div>
          )}

          {!loading && profile && (
            <div className="rounded-2xl border border-[#dfe6e1] bg-white">
              {/* Slug / id row */}
              <div className="border-b border-[#edf0ee] px-6 py-4">
                <div className="flex items-center gap-3">
                  <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#edf8f1] text-[#35664d]">
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
                      <path d="M4 21h16" />
                      <path d="M6 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16" />
                      <path d="M9 7h6" /><path d="M9 11h2" />
                    </svg>
                  </div>
                  <div>
                    <div className="text-sm font-semibold">{profile.name}</div>
                    <div className="text-[11px] text-[#89948e]">
                      Slug: <span className="font-mono">{profile.slug}</span>
                    </div>
                  </div>
                </div>
              </div>

              <form onSubmit={handleSubmit} className="space-y-5 px-6 py-6">

                <div>
                  <label className="mb-1.5 block text-xs font-medium text-[#46534c]">
                    Pharmacy name
                  </label>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Your pharmacy name"
                    minLength={2}
                    maxLength={200}
                    className="h-11 w-full rounded-xl border border-[#dfe6e1] bg-[#fafcfb] px-4 text-sm outline-none transition focus:border-[#35664d] focus:bg-white"
                  />
                </div>

                <div>
                  <label className="mb-1.5 block text-xs font-medium text-[#46534c]">
                    Contact email{" "}
                    <span className="font-normal text-[#9aa39e]">optional</span>
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="pharmacy@example.com"
                    className="h-11 w-full rounded-xl border border-[#dfe6e1] bg-[#fafcfb] px-4 text-sm outline-none transition focus:border-[#35664d] focus:bg-white"
                  />
                </div>

                <div>
                  <label className="mb-1.5 block text-xs font-medium text-[#46534c]">
                    Phone number{" "}
                    <span className="font-normal text-[#9aa39e]">optional</span>
                  </label>
                  <input
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="+1 555 000 0000"
                    maxLength={30}
                    className="h-11 w-full rounded-xl border border-[#dfe6e1] bg-[#fafcfb] px-4 text-sm outline-none transition focus:border-[#35664d] focus:bg-white"
                  />
                </div>

                <div>
                  <label className="mb-1.5 block text-xs font-medium text-[#46534c]">
                    Address{" "}
                    <span className="font-normal text-[#9aa39e]">optional</span>
                  </label>
                  <textarea
                    value={address}
                    onChange={(e) => setAddress(e.target.value)}
                    placeholder="123 Main St, City, State, ZIP"
                    rows={3}
                    maxLength={500}
                    className="w-full rounded-xl border border-[#dfe6e1] bg-[#fafcfb] px-4 py-3 text-sm outline-none transition focus:border-[#35664d] focus:bg-white resize-none"
                  />
                </div>

                {error && (
                  <div className="rounded-xl border border-[#ead8d2] bg-[#fbf5f2] px-4 py-3 text-sm text-[#8b5547]">
                    {error}
                  </div>
                )}

                {saved && (
                  <div className="rounded-xl border border-[#c8e4d0] bg-[#edf8f1] px-4 py-3 text-sm text-[#35664d]">
                    Profile updated successfully.
                  </div>
                )}

                <div className="flex items-center justify-end gap-3 pt-2">
                  <button
                    type="submit"
                    disabled={saving}
                    className="rounded-xl bg-[#17211d] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#26332d] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {saving ? "Saving…" : "Save changes"}
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* Invite team members */}
          <div className="mt-8 rounded-2xl border border-[#dfe6e1] bg-white px-6 py-5">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-semibold">Team members</div>
                <p className="mt-1 text-xs text-[#77847d]">
                  Invite additional pharmacists to join your workspace.
                </p>
              </div>
              <a
                href="/settings/invite"
                className="rounded-xl border border-[#dfe6e1] px-4 py-2 text-xs font-medium text-[#344f42] transition hover:border-[#b8cfc0] hover:bg-[#f7faf8]"
              >
                Invite pharmacist →
              </a>
            </div>
          </div>

        </div>
      </div>
    </AppShell>
  );
}
