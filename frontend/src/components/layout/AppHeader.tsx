"use client";

import { OrganizationSwitcher, UserButton } from "@clerk/nextjs";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { Bell, Menu, Settings, Ship, X } from "lucide-react";
import AppNav from "@/components/layout/AppNav";
import LocaleSwitcher from "@/components/layout/LocaleSwitcher";
import { useFocusTrap } from "@/hooks/useFocusTrap";

export default function AppHeader({ unreadAlerts = 0, orgName }: { unreadAlerts?: number; orgName?: string }) {
  const t = useTranslations();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const menuBtnRef = useRef<HTMLButtonElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // A navigation closes the drawer: adjust state during render, not in an effect.
  const [openedOn, setOpenedOn] = useState(pathname);
  if (open && openedOn !== pathname) {
    setOpenedOn(pathname);
    setOpen(false);
  }
  const openDrawer = () => {
    setOpenedOn(pathname);
    setOpen(true);
  };

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  useEffect(() => {
    if (open) closeBtnRef.current?.focus();
  }, [open]);

  useFocusTrap(open, panelRef, menuBtnRef);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    if (open) window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <header className="bg-white border-b border-slate-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center gap-3 sm:gap-4">
        <button
          ref={menuBtnRef}
          type="button"
          className="md:hidden p-2 -ml-2 rounded-md text-slate-600 hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          aria-expanded={open}
          aria-controls="mobile-nav"
          onClick={openDrawer}
        >
          <Menu className="w-5 h-5" aria-hidden />
          <span className="sr-only">{t("nav.openMenu")}</span>
        </button>

        <Link href="/containers" className="flex items-center gap-2 shrink-0">
          <div className="bg-blue-600 p-1.5 rounded-md">
            <Ship className="w-4 h-4 text-white" />
          </div>
          <span className="text-lg font-semibold tracking-tight hidden sm:inline">
            Freight<span className="text-blue-600">Sight</span>
          </span>
        </Link>

        <div className="min-w-0 flex-1 overflow-x-auto">
          <AppNav unreadAlerts={unreadAlerts} />
        </div>

        <div className="ml-auto flex items-center gap-2 sm:gap-3 text-xs text-slate-500 shrink-0">
          <LocaleSwitcher />
          <Link
            href="/alerts"
            aria-label={t("alerts.bell", { count: unreadAlerts })}
            className="relative p-1.5 rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
          >
            <Bell className="w-4 h-4" />
            {unreadAlerts > 0 ? (
              <span className="absolute -top-0.5 -right-0.5 min-w-4 h-4 px-1 rounded-full bg-amber-500 text-white text-[10px] font-semibold flex items-center justify-center tabular-nums">
                {unreadAlerts > 99 ? "99+" : unreadAlerts}
              </span>
            ) : null}
          </Link>
          <Link
            href="/settings"
            aria-label={t("nav.settings")}
            aria-current={pathname === "/settings" ? "page" : undefined}
            className={`hidden md:inline-flex p-1.5 rounded-md hover:bg-slate-100 hover:text-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 ${pathname === "/settings" ? "bg-slate-100 text-slate-900" : "text-slate-500"}`}
          >
            <Settings className="w-4 h-4" />
          </Link>
          <OrganizationSwitcher hidePersonal afterSelectOrganizationUrl="/containers" afterCreateOrganizationUrl="/containers" />
          <UserButton />
          {orgName ? <span className="sr-only">{orgName}</span> : null}
        </div>
      </div>

      {open ? (
        <div className="md:hidden fixed inset-0 z-50">
          <button
            type="button"
            className="absolute inset-0 bg-slate-900/40"
            aria-label={t("nav.closeMenu")}
            onClick={() => setOpen(false)}
          />
          <div
            ref={panelRef}
            id="mobile-nav"
            role="dialog"
            aria-modal="true"
            aria-label={t("nav.main")}
            className="absolute inset-y-0 left-0 w-[min(100vw-3rem,18rem)] bg-white shadow-xl flex flex-col"
          >
            <div className="flex items-center justify-between px-4 h-14 border-b border-slate-200">
              <span className="font-semibold text-slate-900">FreightSight</span>
              <button
                ref={closeBtnRef}
                type="button"
                className="p-2 rounded-md text-slate-600 hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                onClick={() => setOpen(false)}
              >
                <X className="w-5 h-5" aria-hidden />
                <span className="sr-only">{t("nav.closeMenu")}</span>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-3">
              <AppNav stacked unreadAlerts={unreadAlerts} onNavigate={() => setOpen(false)} />
            </div>
          </div>
        </div>
      ) : null}
    </header>
  );
}
