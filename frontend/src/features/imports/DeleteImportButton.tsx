"use client";

import { useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { btnSecondary } from "@/components/layout/AppShell";
import ConfirmDialog from "@/components/shared/ConfirmDialog";
import { undoImport } from "@/features/actions";
import type { CreatedCounts, DeleteTarget } from "@/features/imports/deleteTarget";

const ROWS = ["products", "orders", "lines", "containers", "loads"] as const;

/**
 * The bin at the end of an import: the wrong file, a month too many, a column read the wrong way round,
 * and what it wrote is wrong — this is the way back, for any kind of file. What the file created is
 * deleted, after a confirmation that says how much; what it only changed keeps its value. A file dropped
 * but never imported wrote nothing and leaves the list at once. A refusal names what stands in the way
 * (a later file, a cost a person added, an ERP document, a closed month) and stays on screen long
 * enough to be read.
 */
export default function DeleteImportButton({ target, labelled = false, onDeleted }: { target: DeleteTarget; labelled?: boolean; onDeleted?: () => void }) {
  const t = useTranslations("imports.undo");
  const locale = useLocale();
  const router = useRouter();
  const trigger = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  const list = (items: string[]) => new Intl.ListFormat(locale === "fr" ? "fr-FR" : "en-GB", { type: "conjunction" }).format(items);
  const said = (counts: Pick<CreatedCounts, (typeof ROWS)[number]>) => ROWS.filter((k) => counts[k] > 0).map((k) => t(`parts.${k}`, { count: counts[k] }));
  const run = () =>
    start(async () => {
      const r = await undoImport(target.id);
      setOpen(false);
      if (!r.ok) return void toast.error(r.error, { duration: 12000 });
      const gone = said(r.data);
      if (r.data.discarded) toast.success(t("discarded"));
      else if (target.kind === "COSTS") toast.success(t("done", { costs: r.data.costs, estimates: r.data.estimates }));
      else toast.success(gone.length ? t("doneRows", { what: list(gone) }) : t("doneNothing"));
      onDeleted?.();
      router.refresh();
    });
  const name = t(target.draft ? "discard" : "action");
  const created = said(target.created);
  const Icon = pending && target.draft ? Loader2 : Trash2;
  return (
    <>
      <button
        ref={trigger}
        type="button"
        onClick={() => (target.draft ? run() : setOpen(true))}
        disabled={pending}
        aria-label={labelled ? undefined : name}
        title={labelled ? undefined : name}
        className={
          labelled
            ? btnSecondary
            : "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-500 hover:bg-red-50 hover:text-red-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 disabled:opacity-50"
        }
      >
        <Icon className={`h-4 w-4 ${labelled ? "mr-2" : ""} ${pending && target.draft ? "animate-spin" : ""}`} aria-hidden />
        {labelled ? name : null}
      </button>
      <ConfirmDialog
        open={open}
        title={t("title")}
        body={
          target.kind === "COSTS"
            ? t("body", { count: target.created.costs, estimates: target.created.estimates })
            : created.length
              ? t("bodyRows", { what: list(created) })
              : t("bodyNothing")
        }
        confirmLabel={t("confirm")}
        cancelLabel={t("cancel")}
        pending={pending}
        returnFocusRef={trigger}
        onCancel={() => setOpen(false)}
        onConfirm={run}
      />
    </>
  );
}
