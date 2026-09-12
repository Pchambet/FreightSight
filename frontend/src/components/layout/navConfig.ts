export type NavItem = {
  href: string;
  key: "containers" | "purchaseOrders" | "imports" | "invoices" | "reports" | "audit" | "alerts" | "settings";
  match: (pathname: string) => boolean;
  badge?: boolean;
};

export const APP_NAV: NavItem[] = [
  { href: "/containers", key: "containers", match: (p) => p === "/containers" || p.startsWith("/container/") },
  { href: "/purchase-orders", key: "purchaseOrders", match: (p) => p === "/purchase-orders" || p.startsWith("/purchase-orders/") },
  { href: "/imports", key: "imports", match: (p) => p === "/imports" || p.startsWith("/imports/") },
  { href: "/invoices", key: "invoices", match: (p) => p === "/invoices" || p.startsWith("/invoices/") },
  { href: "/reports", key: "reports", match: (p) => p === "/reports" || p.startsWith("/reports/") },
  { href: "/audit", key: "audit", match: (p) => p === "/audit" },
  { href: "/alerts", key: "alerts", match: (p) => p === "/alerts", badge: true },
  { href: "/settings", key: "settings", match: (p) => p === "/settings" },
];
