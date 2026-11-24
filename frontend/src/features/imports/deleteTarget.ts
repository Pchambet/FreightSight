import type { ImportJobResponse } from "@/lib/api/client";
import type { ImportKind } from "@/lib/domain";

/** What a file created, as its report counted it: what deleting the import takes away. */
export type CreatedCounts = { costs: number; estimates: number; products: number; orders: number; lines: number; containers: number; loads: number };

/** An import a person can delete, with what the confirmation has to say about it. */
export type DeleteTarget = {
  id: string;
  kind: ImportKind;
  /** Dropped but never imported: nothing was written, so it leaves the list at once, with no question. */
  draft: boolean;
  created: CreatedCounts;
};

/** The deletion an import offers, or none: the API says which imports can still be taken back. */
export function deleteTarget(job: ImportJobResponse): DeleteTarget | null {
  if (!job.can_undo) return null;
  const r = job.report;
  return {
    id: job.id,
    kind: job.kind,
    draft: job.status !== "DONE",
    created: {
      costs: r.costs_created ?? 0,
      estimates: r.estimates_replaced ?? 0,
      products: r.products_created ?? 0,
      orders: r.purchase_orders_created ?? 0,
      lines: r.lines_created ?? 0,
      containers: r.containers_created ?? 0,
      loads: r.loads_created ?? 0,
    },
  };
}
