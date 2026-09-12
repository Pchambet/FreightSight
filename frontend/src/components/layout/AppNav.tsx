"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { APP_NAV } from "@/components/layout/navConfig";

export default function AppNav({
  stacked = false,
  onNavigate,
  unreadAlerts = 0,
}: {
  stacked?: boolean;
  onNavigate?: () => void;
  unreadAlerts?: number;
}) {
  const t = useTranslations("nav");
  const pathname = usePathname();

  return (
    <nav
      className={stacked ? "flex flex-col gap-1" : "hidden md:flex items-center gap-1 text-sm"}
      aria-label={t("main")}
    >
      {APP_NAV.map((n) => {
        const active = n.match(pathname);
        const badge = n.badge && unreadAlerts > 0 ? (unreadAlerts > 99 ? "99+" : unreadAlerts) : null;
        return (
          <Link
            key={n.href}
            href={n.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={
              stacked
                ? `flex items-center gap-2 px-3 py-3 rounded-md text-base transition-colors ${
                    active ? "bg-slate-100 text-slate-900 font-medium" : "text-slate-700 hover:bg-slate-50"
                  }`
                : `inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-colors ${
                    active ? "bg-slate-100 text-slate-900 font-medium" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                  }`
            }
          >
            {t(n.key)}
            {badge ? (
              <span className="min-w-4 h-4 px-1 rounded-full bg-amber-500 text-white text-[10px] font-semibold flex items-center justify-center tabular-nums">
                {badge}
              </span>
            ) : null}
          </Link>
        );
      })}
    </nav>
  );
}
