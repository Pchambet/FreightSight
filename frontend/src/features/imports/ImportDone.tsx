"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { btnSecondary } from "@/components/layout/AppShell";
import UndoImportButton from "@/features/imports/UndoImportButton";
import type { ImportJobResponse } from "@/lib/api/client";
import { money } from "@/lib/format";

/** How many orders without a rate are named one by one; the rest are counted. */
const NAMED = 8;

/** Where what a file brought is looked at. A price list changes no screen by itself: the next file does. */
const SEE: Partial<Record<ImportJobResponse["kind"], { href: string; key: "goToOrders" | "goToContainers" | "prepareAudit" }>> = {
  PURCHASE_ORDERS: { href: "/purchase-orders", key: "goToOrders" },
  LEGACY_PO_CONTAINER: { href: "/purchase-orders", key: "goToOrders" },
  CONTAINERS: { href: "/containers", key: "goToContainers" },
  COSTS: { href: "/cost-audit", key: "prepareAudit" },
};

/**
 * What the import unlocked, in words — « 23 conteneurs datés », « 212 coûts créés pour 48 310,00 € » —
 * what it means for the files that follow, where to look at it, and, for a costs file, the way back.
 * The orders a file left without a rate are named, each a link, since each needs one. The next file is
 * not a button here: its step, with its drop zone, is right below.
 */
export default function ImportDone({ job, baseCurrency }: { job: ImportJobResponse; baseCurrency: string }) {
  const t = useTranslations("importWizard.done");
  const locale = useLocale();
  const router = useRouter();
  const r = job.report;
  const skipped = new Set((r.errors ?? []).map((e) => e.row)).size;
  const lines: string[] = [];
  switch (job.kind) {
    case "PRODUCTS":
      lines.push(t("products", { created: r.products_created ?? 0, updated: r.products_updated ?? 0 }));
      break;
    case "CONTAINERS":
      lines.push(t("containers", { created: r.containers_created ?? 0, updated: r.containers_updated ?? 0, dated: r.containers_dated ?? 0 }));
      lines.push(t("shipments", { shipments: r.shipments_created ?? 0, loads: r.loads_created ?? 0 }));
      if (r.invoices_matched) lines.push(t("invoicesMatched", { count: r.invoices_matched }));
      if (r.po_split) lines.push(t("poSplit", { count: r.po_split }));
      break;
    case "COSTS": {
      // The total leaves out the import VAT the file brought: tracked, never a landed cost.
      lines.push(t("costs", { created: r.costs_created ?? 0, amount: money(r.money?.total_base ?? "0", baseCurrency, locale), vat: r.money?.by_type?.some((x) => x.cost_type === "IMPORT_VAT") ? "yes" : "no" }));
      if (r.costs_skipped) lines.push(t("costsSkipped", { count: r.costs_skipped }));
      if (r.estimates_replaced) lines.push(t("estimatesReplaced", { count: r.estimates_replaced }));
      // A credit note that cancels a cost still counted asks for that cost to go; the others only for a look.
      const credits = r.credit_notes_skipped ?? [];
      const reversing = credits.filter((c) => c.reverses_cost_id).length;
      if (reversing) lines.push(t("creditReverses", { count: reversing }));
      if (credits.length > reversing) lines.push(t("creditNotes", { count: credits.length - reversing }));
      break;
    }
    default:
      lines.push(t("summary", { pos: r.purchase_orders_created ?? 0, lines: r.lines_created ?? 0, containers: r.containers_created ?? 0, loads: r.loads_created ?? 0 }));
  }
  if (skipped) lines.push(t("skipped", { rows: skipped }));
  const withoutRate = job.kind === "PURCHASE_ORDERS" ? (r.orders_without_rate ?? []) : [];
  // Whether a file of orders puts them in containers is whether it has a container column: a file read
  // again creates and changes no load, yet its orders are in their containers all the same.
  const unloaded = job.kind === "PURCHASE_ORDERS" && !job.mapping.container_number;
  const see = SEE[job.kind];
  const canUndo = job.kind === "COSTS" && job.can_undo;
  return (
    <div className="p-5 space-y-4 text-sm">
      <ul className="space-y-1 text-slate-800">
        {lines.map((l) => <li key={l}>{l}</li>)}
        {withoutRate.length ? (
          <li className="text-amber-800">
            {t("withoutRate", { count: withoutRate.length })}{" "}
            {withoutRate.slice(0, NAMED).map((po, i) => (
              <span key={po}>{i ? ", " : ""}<Link href={`/purchase-orders?q=${encodeURIComponent(po)}`} className="font-medium underline underline-offset-2 hover:no-underline">{po}</Link></span>
            ))}
            {withoutRate.length > NAMED ? ` ${t("withoutRateMore", { count: withoutRate.length - NAMED })}` : null}
          </li>
        ) : null}
      </ul>
      <p className="text-slate-600">{unloaded ? t("meansUnloaded") : t("means", { kind: job.kind })}</p>
      {see || canUndo ? (
        <div className="flex flex-wrap items-center gap-2">
          {see ? <Link href={see.href} className={btnSecondary}>{t(see.key)}</Link> : null}
          {canUndo ? <UndoImportButton importId={job.id} costCount={r.costs_created ?? 0} estimatesReplaced={r.estimates_replaced ?? 0} onUndone={() => router.push("/imports")} /> : null}
        </div>
      ) : null}
    </div>
  );
}
