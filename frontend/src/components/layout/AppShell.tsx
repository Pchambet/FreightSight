import { OrganizationSwitcher, UserButton } from "@clerk/nextjs";
import Link from "next/link";
import { Ship } from "lucide-react";

const NAV = [
  { href: "/containers", label: "Containers" },
  { href: "/purchase-orders", label: "Purchase orders" },
  { href: "/imports", label: "Imports" },
  { href: "/settings", label: "Settings" },
];

export function AppShell({ children, orgName }: { children: React.ReactNode; orgName?: string }) {
  return (
    <div className="min-h-screen">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center gap-8">
          <Link href="/containers" className="flex items-center gap-2">
            <div className="bg-blue-600 p-1.5 rounded-md">
              <Ship className="w-4 h-4 text-white" />
            </div>
            <span className="text-lg font-semibold tracking-tight">
              Freight<span className="text-blue-600">Sight</span>
            </span>
          </Link>
          <nav className="flex items-center gap-1 text-sm">
            {NAV.map((n) => (
              <Link key={n.href} href={n.href} className="px-3 py-1.5 rounded-md text-slate-600 hover:bg-slate-100 hover:text-slate-900">
                {n.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-xs text-slate-500">
            <span className="hidden sm:inline">Pre-alpha</span>
            <OrganizationSwitcher hidePersonal afterSelectOrganizationUrl="/containers" afterCreateOrganizationUrl="/containers" />
            <UserButton />
            {orgName ? <span className="sr-only">{orgName}</span> : null}
          </div>
        </div>
      </header>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">{children}</div>
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: React.ReactNode; subtitle?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-6">
      <div>
        <h1 className="text-2xl font-semibold">{title}</h1>
        {subtitle ? <p className="text-slate-500 mt-1 text-sm">{subtitle}</p> : null}
      </div>
      {actions}
    </div>
  );
}

export function Card({ title, right, children, className }: { title?: React.ReactNode; right?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-white rounded-lg border border-slate-200 overflow-hidden ${className ?? ""}`}>
      {title ? (
        <div className="px-5 py-3.5 border-b border-slate-200 flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">{title}</h2>
          {right}
        </div>
      ) : null}
      {children}
    </div>
  );
}

export const th = "px-4 py-2.5 text-left text-xs font-medium text-slate-500 uppercase tracking-wider whitespace-nowrap";
export const thRight = `${th} text-right`;
export const td = "px-4 py-2.5 whitespace-nowrap";
export const tdRight = `${td} text-right tabular-nums`;
export const input = "w-full border border-slate-300 rounded-md px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none";
export const label = "block text-xs font-medium text-slate-600 mb-1";
export const btnPrimary = "inline-flex items-center justify-center bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white text-sm font-medium py-2 px-4 rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500 focus-visible:ring-offset-2";
export const btnSecondary = "inline-flex items-center justify-center bg-white hover:bg-slate-50 disabled:opacity-50 text-slate-700 text-sm font-medium py-2 px-4 rounded-md border border-slate-300";
