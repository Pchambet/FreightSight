import { getLocale, getTranslations } from "next-intl/server";
import type { ImportJobResponse } from "@/lib/api/client";
import type { ImportKind } from "@/lib/domain";
import { dateShort, money } from "@/lib/format";

type Translate = Awaited<ReturnType<typeof getTranslations<"imports">>>;

/** What an import of this kind did, in one line: the history's column, and a step's « done » line. */
export function importResultLine(job: ImportJobResponse, t: Translate, baseCurrency: string, locale: string): string {
  const r = job.report;
  switch (job.kind) {
    case "PRODUCTS":
      return t("resultProducts", { created: r.products_created ?? 0, updated: r.products_updated ?? 0 });
    case "CONTAINERS":
      return t("resultContainers", { created: r.containers_created ?? 0, updated: r.containers_updated ?? 0, dated: r.containers_dated ?? 0 });
    case "COSTS":
      return t("resultCosts", { count: r.costs_created ?? 0, amount: money(r.money?.total_base ?? "0", baseCurrency, locale), vat: r.money?.by_type?.some((x) => x.cost_type === "IMPORT_VAT") ? "yes" : "no" });
    default:
      return t("result", { pos: r.purchase_orders_created ?? 0, lines: r.lines_created ?? 0, containers: r.containers_created ?? 0, loads: r.loads_created ?? 0 });
  }
}

/**
 * Where one of the files stands: the last one of its kind that went in and was not taken back, and a
 * file dropped since that is still waiting to be imported.
 */
export type ImportStepState = {
  done: { file: string; date: string; result: string } | null;
  waiting: { id: string; file: string } | null;
};

/** The state of each kind's step, from the import history (most recent first, as the API lists it). */
export async function importStepStates(jobs: ImportJobResponse[], baseCurrency: string): Promise<Partial<Record<ImportKind, ImportStepState>>> {
  const [t, tc, locale] = await Promise.all([getTranslations("imports"), getTranslations("common"), getLocale()]);
  const name = (j: ImportJobResponse) => (j.source === "erp_sync" ? t("source.erp_sync") : (j.original_filename ?? tc("empty")));
  const states: Partial<Record<ImportKind, ImportStepState>> = {};
  for (const j of [...jobs].sort((a, b) => b.created_at.localeCompare(a.created_at))) {
    const state = (states[j.kind] ??= { done: null, waiting: null });
    if (j.status === "DONE" && !j.undone_at) {
      state.done ??= { file: name(j), date: dateShort(j.committed_at ?? j.created_at, locale), result: importResultLine(j, t, baseCurrency, locale) };
    } else if ((j.status === "PARSED" || j.status === "VALIDATED") && !state.done) {
      // Only a file dropped after the last one that went in: an older one left on the way is history.
      state.waiting ??= { id: j.id, file: name(j) };
    }
  }
  return states;
}
