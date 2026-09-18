"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import {
  fetchMe,
  getRoleHome,
  getUser,
  isAuthenticated,
  logout,
  User,
} from "../lib/auth";

type NavItem = {
  label: string;
  href: string;
  icon: ReactNode;
};

function Icon({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <span className="grid h-8 w-8 shrink-0 place-items-center">
      {children}
    </span>
  );
}

function PharmacyIcon() {
  return (
    <Icon>
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
      >
        <path d="M4 21h16" />
        <path d="M6 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16" />
        <path d="M9 7h6" />
        <path d="M9 11h2" />
        <path d="M13 11h2" />
        <path d="M9 15h2" />
        <path d="M13 15h2" />
      </svg>
    </Icon>
  );
}

function HomeIcon() {
  return (
    <Icon>
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
      >
        <path d="m3 10 9-7 9 7" />
        <path d="M5 9v11h14V9" />
        <path d="M9 20v-6h6v6" />
      </svg>
    </Icon>
  );
}

function AnalyzeIcon() {
  return (
    <Icon>
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
      >
        <path d="M4 5h16v14H4z" />
        <path d="M8 9h8" />
        <path d="M8 13h5" />
        <path d="M16 16l2 2" />
        <circle cx="15" cy="15" r="3" />
      </svg>
    </Icon>
  );
}

function HistoryIcon() {
  return (
    <Icon>
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
      >
        <path d="M4 12a8 8 0 1 0 2.3-5.7" />
        <path d="M4 5v5h5" />
        <path d="M12 7v5l3 2" />
      </svg>
    </Icon>
  );
}

function CustomersIcon() {
  return (
    <Icon>
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
      >
        <circle cx="9" cy="8" r="3" />
        <path d="M3.5 20c.7-3.5 2.5-5.3 5.5-5.3s4.8 1.8 5.5 5.3" />
        <path d="M16 5.5a3 3 0 0 1 0 5.8" />
        <path d="M17 14.7c2.2.4 3.5 2.1 4 5.3" />
      </svg>
    </Icon>
  );
}

function PrescriptionIcon() {
  return (
    <Icon>
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
      >
        <rect x="5" y="3" width="14" height="18" rx="2" />
        <path d="M9 7h6" />
        <path d="M9 11h6" />
        <path d="M9 15h3" />
      </svg>
    </Icon>
  );
}

function PharmacyLinkIcon() {
  return (
    <Icon>
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
      >
        <path d="M4 21h16" />
        <path d="M6 21V6l6-3 6 3v15" />
        <path d="M9 10h6" />
        <path d="M12 7v6" />
      </svg>
    </Icon>
  );
}

function UsersIcon() {
  return (
    <Icon>
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
      >
        <circle cx="9" cy="8" r="3" />
        <circle cx="17" cy="9" r="2.5" />
        <path d="M3.5 20c.7-3.5 2.5-5.3 5.5-5.3s4.8 1.8 5.5 5.3" />
        <path d="M15 15.5c2.4.2 4.1 1.7 5 4.5" />
      </svg>
    </Icon>
  );
}

function AuditIcon() {
  return (
    <Icon>
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
      >
        <path d="M7 3h10l3 3v15H4V3z" />
        <path d="M7 3v5h10V3" />
        <path d="M8 12h8" />
        <path d="M8 16h6" />
      </svg>
    </Icon>
  );
}

function ProfileIcon() {
  return (
    <Icon>
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
      >
        <circle cx="12" cy="8" r="3.2" />
        <path d="M5 21c.8-4.2 3.1-6.3 7-6.3s6.2 2.1 7 6.3" />
      </svg>
    </Icon>
  );
}

function getNavigation(role: string): NavItem[] {
  if (role === "customer") {
    return [
      {
        label: "Overview",
        href: "/customer",
        icon: <HomeIcon />,
      },
      {
        label: "My prescriptions",
        href: "/customer/prescriptions",
        icon: <PrescriptionIcon />,
      },
      {
        label: "Profile",
        href: "/customer/profile",
        icon: <ProfileIcon />,
      },
    ];
  }

  if (role === "admin") {
    return [
      {
        label: "Admin overview",
        href: "/admin",
        icon: <HomeIcon />,
      },
      {
        label: "Users",
        href: "/admin/users",
        icon: <UsersIcon />,
      },
      {
        label: "Pharmacies",
        href: "/admin/pharmacies",
        icon: <PharmacyIcon />,
      },
      {
        label: "Prescription reviews",
        href: "/admin/reviews",
        icon: <PrescriptionIcon />,
      },
      {
        label: "Audit log",
        href: "/admin/audit",
        icon: <AuditIcon />,
      },
    ];
  }

  return [
    {
      label: "Dashboard",
      href: "/dashboard",
      icon: <HomeIcon />,
    },
    {
      label: "Analyze prescription",
      href: "/analyze",
      icon: <AnalyzeIcon />,
    },
    {
      label: "History",
      href: "/history",
      icon: <HistoryIcon />,
    },
    {
      label: "Review queue",
      href: "/history?review_status=pending",
      icon: <PrescriptionIcon />,
    },
    {
      label: "Customers",
      href: "/customers",
      icon: <CustomersIcon />,
    },
    {
      label: "Settings",
      href: "/settings/organization",
      icon: <ProfileIcon />,
    },
  ];
}

function roleLabel(role: string) {
  if (role === "customer") return "Customer";
  if (role === "admin") return "Administrator";
  return "Pharmacy";
}

function getAllowedWorkspace(pathname: string) {
  if (
    pathname === "/dashboard" ||
    pathname.startsWith("/dashboard/") ||
    pathname === "/analyze" ||
    pathname.startsWith("/analyze/") ||
    pathname === "/history" ||
    pathname.startsWith("/history/") ||
    pathname === "/customers" ||
    pathname.startsWith("/customers/") ||
    pathname === "/analysis" ||
    pathname.startsWith("/analysis/") ||
    pathname === "/review" ||
    pathname.startsWith("/review/") ||
    pathname === "/settings" ||
    pathname.startsWith("/settings/")
  ) {
    return "pharmacist";
  }

  if (
    pathname === "/customer" ||
    pathname.startsWith("/customer/")
  ) {
    return "customer";
  }

  if (
    pathname === "/admin" ||
    pathname.startsWith("/admin/")
  ) {
    return "admin";
  }

  return null;
}

export default function AppShell({
  children,
}: {
  children: ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();

  const [user, setUser] = useState<User | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    async function loadUser() {
      if (!isAuthenticated()) {
        if (active) {
          setLoading(false);
        }
        return;
      }

      try {
        const currentUser = await fetchMe();

        if (active) {
          setUser(currentUser);
        }
      } catch {
        if (active) {
          setUser(getUser());
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    loadUser();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (loading || !user) {
        return;
    }

    // Admin login is intentionally public.
    if (pathname === "/admin/login") {
        return;
    }

    const requiredRole = getAllowedWorkspace(pathname);

    if (!requiredRole) {
        return;
    }

    if (user.role !== requiredRole) {
        router.replace(getRoleHome(user));
    }
    }, [loading, user, pathname, router]);

  if (loading) {
    return (
      <main className="min-h-screen bg-[#f4f7f5]">
        <div className="flex min-h-screen items-center justify-center">
          <div className="flex items-center gap-3 text-sm text-[#718078]">
            <span className="h-2 w-2 animate-pulse rounded-full bg-[#35664d]" />
            Loading workspace…
          </div>
        </div>
      </main>
    );
  }

  const publicRoute =
    pathname === "/" ||
    pathname === "/login" ||
    pathname === "/sign-in" ||
    pathname === "/sign-up" ||
    pathname === "/signup" ||
    pathname.startsWith("/signup/") ||
    pathname === "/forgot-password" ||
    pathname === "/verify-email" ||
    pathname === "/accept-invite" ||
    pathname === "/admin/login";

    if (!user || publicRoute) {
        return <>{children}</>;
    }

  const navigation = getNavigation(user.role);

  const roleHome = getRoleHome(user);

  function isActive(item: NavItem) {
    if (item.href === roleHome) {
      return pathname === item.href;
    }

    return pathname === item.href || pathname.startsWith(`${item.href}/`);
  }

  function handleProfile() {
    if (!user) return;

    if (user.role === "customer") {
      router.push("/customer");
      return;
    }

    if (user.role === "admin") {
      router.push("/admin");
      return;
    }

    router.push("/dashboard");
  }

  function handleLogout() {
    logout();
  }

  return (
    <div className="min-h-screen bg-[#f4f7f5] text-[#17211d]">

      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-[250px] border-r border-[#dfe6e1] bg-white lg:flex lg:flex-col">

        <div className="flex h-[76px] items-center border-b border-[#edf0ee] px-6">
          <Link href={roleHome} className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-[#17211d] text-xs font-semibold text-white">
              Rx
            </span>

            <div>
              <div className="text-sm font-semibold">
                Prescription Intelligence
              </div>

              <div className="text-[9px] uppercase tracking-[0.16em] text-[#89948e]">
                {roleLabel(user.role)} workspace
              </div>
            </div>
          </Link>
        </div>

        <div className="flex-1 px-3 py-5">
          <div className="mb-3 px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-[#9aa39e]">
            Workspace
          </div>

          <nav className="space-y-1">
            {navigation.map((item) => {
              const active = isActive(item);

              return (
                <Link
                  key={`${item.label}-${item.href}`}
                  href={item.href}
                  className={[
                    "flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm transition",
                    active
                      ? "bg-[#edf8f1] font-medium text-[#35664d]"
                      : "text-[#66736c] hover:bg-[#f7f9f8] hover:text-[#17211d]",
                  ].join(" ")}
                >
                  {item.icon}
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="border-t border-[#edf0ee] p-3">

          <button
            type="button"
            onClick={handleProfile}
            className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition hover:bg-[#f7f9f8]"
          >
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#edf8f1] text-xs font-semibold text-[#35664d]">
              {user.name?.charAt(0)?.toUpperCase() || "U"}
            </span>

            <span className="min-w-0 flex-1">
              <span className="block truncate text-xs font-medium text-[#354139]">
                {user.name}
              </span>

              <span className="block truncate text-[10px] text-[#89948e]">
                {user.email}
              </span>
            </span>
          </button>

          <button
            type="button"
            onClick={handleLogout}
            className="mt-1 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-xs text-[#7c8881] transition hover:bg-[#fbf5f2] hover:text-[#8b5547]"
          >
            <span className="grid h-8 w-8 place-items-center">
              <svg
                width="17"
                height="17"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
              >
                <path d="M10 17l5-5-5-5" />
                <path d="M15 12H3" />
                <path d="M21 3v18" />
              </svg>
            </span>
            Sign out
          </button>
        </div>
      </aside>

      {/* Mobile header */}
      <header className="sticky top-0 z-40 flex h-[68px] items-center justify-between border-b border-[#dfe6e1] bg-white/95 px-4 backdrop-blur lg:hidden">

        <Link href={roleHome} className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-[#17211d] text-xs font-semibold text-white">
            Rx
          </span>

          <div>
            <div className="text-sm font-semibold">
              Prescription Intelligence
            </div>

            <div className="text-[9px] uppercase tracking-[0.14em] text-[#89948e]">
              {roleLabel(user.role)}
            </div>
          </div>
        </Link>

        <button
          type="button"
          onClick={() => setMobileOpen((value) => !value)}
          aria-label="Open navigation"
          className="grid h-10 w-10 place-items-center rounded-xl border border-[#dfe6e1] text-[#526158]"
        >
          {mobileOpen ? (
            <svg
              width="19"
              height="19"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.7"
            >
              <path d="M6 6l12 12" />
              <path d="M18 6 6 18" />
            </svg>
          ) : (
            <svg
              width="19"
              height="19"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.7"
            >
              <path d="M4 7h16" />
              <path d="M4 12h16" />
              <path d="M4 17h16" />
            </svg>
          )}
        </button>
      </header>

      {/* Mobile navigation */}
      {mobileOpen && (
        <div className="fixed inset-x-0 top-[68px] z-30 border-b border-[#dfe6e1] bg-white px-4 py-4 shadow-[0_20px_45px_rgba(30,45,38,0.08)] lg:hidden">

          <div className="mb-3 px-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-[#9aa39e]">
            Workspace
          </div>

          <nav className="space-y-1">
            {navigation.map((item) => {
              const active = isActive(item);

              return (
                <Link
                  key={`${item.label}-${item.href}-mobile`}
                  href={item.href}
                  className={[
                    "flex items-center gap-2 rounded-xl px-3 py-3 text-sm",
                    active
                      ? "bg-[#edf8f1] font-medium text-[#35664d]"
                      : "text-[#66736c]",
                  ].join(" ")}
                >
                  {item.icon}
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="mt-4 border-t border-[#edf0ee] pt-4">
            <button
              type="button"
              onClick={handleProfile}
              className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left"
            >
              <span className="grid h-9 w-9 place-items-center rounded-full bg-[#edf8f1] text-xs font-semibold text-[#35664d]">
                {user.name?.charAt(0)?.toUpperCase() || "U"}
              </span>

              <span>
                <span className="block text-xs font-medium">
                  {user.name}
                </span>
                <span className="block text-[10px] text-[#89948e]">
                  {roleLabel(user.role)}
                </span>
              </span>
            </button>

            <button
              type="button"
              onClick={handleLogout}
              className="mt-2 w-full rounded-xl px-3 py-2 text-left text-xs text-[#8b5547]"
            >
              Sign out
            </button>
          </div>
        </div>
      )}

      {/* Main content */}
      <main className="min-h-screen lg:pl-[250px]">
        {children}
      </main>
    </div>
  );
}