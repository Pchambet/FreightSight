"use client";

import { useMemo, useState, useTransition } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Card, btnPrimary, btnSecondary, input, label } from "@/components/layout/AppShell";
import NextStepCard from "@/components/shared/NextStepCard";
import { commitImport, validateImport } from "@/features/actions";
import { unreadColumns } from "@/features/imports/columns";
import CostsPreview from "@/features/imports/CostsPreview";
import ImportDone from "@/features/imports/ImportDone";
import ImportSteps from "@/features/imports/ImportSteps";
import IssueGroups, { useIssueSentence } from "@/features/imports/IssueGroups";
import type { ImportStepState } from "@/features/imports/stepStates";
import { ordersWithoutRateStep } from "@/features/workflow/steps";
import type { ImportJobResponse, Schemas } from "@/lib/api/client";
import { COST_TYPES, type CostType, type ImportKind } from "@/lib/domain";
import { money } from "@/lib/format";

type Step = "mapping" | "review" | "done";
type KindInfo = Schemas["ImportKindInfo"];
type Field = Schemas["ImportFieldInfo"];
type Report = Schemas["ImportReport"];

const STEPS: Step[] = ["mapping", "review", "done"];

/**
 * Where a file's screen opens, from what its import already holds: on the summary once it went in, on
 * the preview when one stands — a file whose columns read themselves is previewed as it is dropped —
 * and on the columns otherwise. A preview that refused every row kept those refusals: they are the
 * answer, so the preview opens on them, import disabled.
 */
function opening(job: ImportJobResponse): { job: ImportJobResponse; step: Step } {
  if (job.status === "DONE") return { job, step: "done" };
  if (job.status === "VALIDATED") return { job, step: "review" };
  const refused = job.report.code === "NO_VALID_ROWS" ? (job.report.report as Report | undefined) : undefined;
  return refused ? { job: { ...job, report: refused }, step: "review" } : { job, step: "mapping" };
}

/**
 * One file of a quarter, once it is dropped on its step: its columns when a person has something to
 * decide about them, a preview that writes nothing, then the import and what it unlocked, with the
 * next file's step right below. The kinds and their columns come from the API (`/imports/kinds`),
 * named with the same headers as the templates and the exports. The preview is mandatory and is what
 * gets committed: the costs file's default type and per-wording types are kept on the job; if the
 * figures moved in between, the API refuses (PREVIEW_CHANGED) and the new preview is shown for another
 * look — never imported behind the person's back.
 */
export default function ImportWizard({
  kinds,
  initialJob,
  initialMappingError,
  states,
  baseCurrency,
}: {
  kinds: KindInfo[];
  initialJob: ImportJobResponse;
  /** The last preview's refusal of the whole file, in words: it is about the columns, and said there. */
  initialMappingError: string | null;
  states: Partial<Record<ImportKind, ImportStepState>>;
  baseCurrency: string;
}) {
  const t = useTranslations("importWizard");
  const costTypeLabel = useTranslations("domain.costType");
  const wt = useTranslations("workflow");
  const wLabel = (key: string, params?: Record<string, string | number>) => wt(key as never, params as never);
  const router = useRouter();
  const locale = useLocale();
  const [opened] = useState(() => opening(initialJob));
  const options = (initialJob.options ?? {}) as { default_cost_type?: CostType | null; label_types?: Record<string, CostType>; force_duplicates?: boolean };
  const [job, setJob] = useState<ImportJobResponse>(opened.job);
  const [step, setStep] = useState<Step>(opened.step);
  const [mapping, setMapping] = useState<Record<string, string>>(initialJob.mapping);
  const [defaultCostType, setDefaultCostType] = useState<CostType | "">(options.default_cost_type ?? "");
  const [labelTypes, setLabelTypes] = useState<Record<string, CostType>>(options.label_types ?? {});
  // A person's word that lines refused as a possible double entry are other invoices: kept on the job,
  // so the commit writes them too, and logged with the import.
  const [forceDuplicates, setForceDuplicates] = useState(options.force_duplicates ?? false);
  // A refusal of the whole file at the preview (a tax-included amount column…) is about the mapping:
  // said where the mapping is, until it changes.
  const [mappingError, setMappingError] = useState<string | null>(opened.step === "mapping" ? initialMappingError : null);
  const [changed, setChanged] = useState<{ before: Report; after: Report } | null>(null);
  const [pending, startTransition] = useTransition();

  const info = kinds.find((k) => k.kind === job.kind);
  const fields = useMemo(() => info?.fields ?? [], [info]);
  // The same words as the template's and the exports' columns, in the reader's language: this kind's
  // header first, another kind's for a field it does not list.
  const fieldName = (field: string) => {
    const f = fields.find((x) => x.field === field) ?? kinds.flatMap((k) => k.fields).find((x) => x.field === field);
    return f ? (locale === "fr" ? f.header_fr : f.header_en) : field;
  };
  const issueSentence = useIssueSentence(job.kind, fieldName, baseCurrency);
  const report = job.report;
  const errors = report.errors ?? [];
  const warnings = report.warnings ?? [];
  // Whether a value is per unit or for the whole line is exactly what the dropdown decides, so the
  // warning sits beside it once a preview has detected the ambiguity — or a weight column left unread
  // because only a person can say which it is.
  const unitColumnWarning = (field: string) => warnings.find((w) => (w.code === "UNIT_COLUMN_AMBIGUOUS" || w.code === "UNIT_COLUMN_UNMAPPED") && w.field === field);
  // What the import leaves out is the report's own count, not the rows that carry an error: a box or a
  // bill refused whole drops rows with no error of their own, and so does a refund with the line it cancels.
  const leftOut = Math.max(report.row_count - report.valid_rows, 0);
  const leftWithoutError = Math.max(leftOut - new Set(errors.map((e) => e.row)).size, 0);
  const missingRequired = fields.filter((f) => f.required && !mapping[f.field]).map((f) => fieldName(f.field));
  const oneOf = info?.required_one_of ?? [];
  const missingOneOf = oneOf.filter((group) => !group.some((f) => mapping[f])).map((group) => group.map(fieldName));
  const unread = unreadColumns(job.columns, mapping);
  // The optional fields the file had no column for when the screen opened are folded away: a list of
  // « no column » read as a list of problems. Frozen at opening, so a field does not jump out of the
  // fold while its column is being chosen. A field a group needs one of stays in sight until one is set.
  const [foldedAtOpening] = useState(() => {
    const needed = new Set(oneOf.filter((group) => !group.some((f) => initialJob.mapping[f])).flat());
    return new Set(fields.filter((f) => !f.required && !initialJob.mapping[f.field] && !needed.has(f.field)).map((f) => f.field));
  });
  const folded = (f: Field) => foldedAtOpening.has(f.field) && !unitColumnWarning(f.field);

  const validate = (next: { labelTypes?: Record<string, CostType>; forceDuplicates?: boolean } = {}) => {
    const types = next.labelTypes ?? labelTypes;
    const force = next.forceDuplicates ?? forceDuplicates;
    startTransition(async () => {
      const result = await validateImport(job.id, mapping, { defaultCostType: defaultCostType || null, labelTypes: types, forceDuplicates: force });
      if (!result.ok && "report" in result) {
        // Nothing to import, but the refusals are the answer: the review shows them, import disabled.
        setMappingError(null);
        setLabelTypes(types);
        setForceDuplicates(force);
        setJob({ ...job, report: result.report });
        setChanged(null);
        setStep("review");
        return;
      }
      if (!result.ok) {
        const message = "oneOf" in result ? t("mapping.oneOf", { count: result.oneOf.length, fields: result.oneOf.map(fieldName).join(", ") }) : result.error;
        if (step !== "mapping") toast.error(message);
        setMappingError(message);
        return;
      }
      setMappingError(null);
      setLabelTypes(types);
      setForceDuplicates(force);
      setJob(result.data);
      setChanged(null);
      setStep("review");
    });
  };

  const commit = (onError: "skip_rows" | "abort") => {
    startTransition(async () => {
      const result = await commitImport(job.id, onError, job.preview_key ?? null);
      if (!result.ok) {
        if (result.code === "PREVIEW_CHANGED" && result.report) {
          // The new preview, and the key that commits exactly it: the next click imports what is shown.
          setChanged({ before: job.report, after: result.report });
          setJob({ ...job, report: result.report, preview_key: result.previewKey ?? job.preview_key });
          return;
        }
        return void toast.error(result.error);
      }
      setJob(result.data);
      setStep("done");
      toast.success(t("done.committed"));
      router.refresh();
    });
  };

  // The figures the preview shows first, by kind: what the import would create or change.
  const figures = (r: Report): [string, string][] => {
    const valid: [string, string] = [t("review.validRows"), `${r.valid_rows} / ${r.row_count}`];
    switch (job.kind) {
      case "PRODUCTS":
        return [valid, [t("review.products"), t("review.newUpdated", { created: r.products_created ?? 0, updated: r.products_updated ?? 0 })]];
      case "CONTAINERS":
        return [
          valid,
          [t("review.containers"), t("review.newUpdatedMasculine", { created: r.containers_created ?? 0, updated: r.containers_updated ?? 0 })],
          [t("review.dated"), String(r.containers_dated ?? 0)],
          [t("review.shipmentsLoads"), `${r.shipments_created ?? 0} / ${r.loads_created ?? 0}`],
        ];
      case "COSTS":
        return [
          valid,
          [t("review.costs"), String(r.costs_created ?? 0)],
          [t("review.costsSkipped"), String(r.costs_skipped ?? 0)],
          [t("review.estimatesReplaced"), String(r.estimates_replaced ?? 0)],
        ];
      default:
        return [
          valid,
          [t("review.purchaseOrders"), t("review.newUpdated", { created: r.purchase_orders_created ?? 0, updated: r.purchase_orders_updated ?? 0 })],
          [t("review.lines"), t("review.newUpdated", { created: r.lines_created ?? 0, updated: r.lines_updated ?? 0 })],
          [t("review.containersLoads"), `${r.containers_created ?? 0} / ${(r.loads_created ?? 0) + (r.loads_updated ?? 0)}`],
        ];
    }
  };
  // Before → after, in money for a costs file, in rows otherwise.
  const changedFigure = (r: Report) => (r.money ? money(r.money.total_base, baseCurrency, locale) : t("review.rowsCount", { count: r.valid_rows }));

  // An order left without a rate has no value, and every charge split by value on its boxes waits for
  // it: that comes before the next file.
  const withoutRate = step === "done" && job.kind === "PURCHASE_ORDERS" ? ordersWithoutRateStep(job.report.orders_without_rate ?? []) : null;

  const mappingField = (f: Field) => {
    const warning = unitColumnWarning(f.field);
    return (
      <div key={f.field} className="flex flex-col gap-1">
        <div className="flex items-center gap-3">
          <label htmlFor={`map-${f.field}`} className="w-44 text-sm text-slate-700 shrink-0">{fieldName(f.field)}{f.required ? <span className="text-red-600" aria-hidden> *</span> : null}{f.required ? <span className="sr-only"> {t("mapping.requiredMark")}</span> : null}</label>
          <select id={`map-${f.field}`} value={mapping[f.field] ?? ""} onChange={(e) => { setMappingError(null); setMapping((m) => { const n = { ...m }; if (e.target.value) n[f.field] = e.target.value; else delete n[f.field]; return n; }); }} className={input}>
            <option value="">{t("mapping.notInFile")}</option>
            {job.columns.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        {warning ? <p className="text-xs text-amber-700 pl-[calc(11rem+0.75rem)]">{issueSentence(warning)}</p> : null}
      </div>
    );
  };
  const inSight = fields.filter((f) => !folded(f));
  const foldedFields = fields.filter(folded);

  return (
    <div className="space-y-6">
      {withoutRate ? (
        <NextStepCard
          title={wt("nextStep")}
          description={wLabel(withoutRate.descriptionKey, withoutRate.descriptionParams)}
          variant={withoutRate.variant}
          primary={withoutRate.primary && { href: withoutRate.primary.href, label: wLabel(withoutRate.primary.labelKey, withoutRate.primary.labelParams) }}
          secondary={withoutRate.secondary.map((s) => ({ href: s.href, label: wLabel(s.labelKey, s.labelParams) }))}
        />
      ) : null}
      <ol className="flex flex-wrap gap-2 text-xs">
        {STEPS.map((s) => (
          <li key={s} aria-current={s === step ? "step" : undefined} className={`px-3 py-1.5 rounded-md border ${s === step ? "bg-slate-900 text-white border-slate-900" : "bg-white text-slate-500 border-slate-200"}`}>{t(`steps.${s}`)}</li>
        ))}
      </ol>

      {step === "mapping" ? (
        <Card title={t("mapping.card")} right={<span className="text-xs text-slate-500">{t("mapping.meta", { rows: job.row_count, encoding: job.encoding ?? "" })}{job.delimiter ? ` · "${job.delimiter}"` : ""}</span>}>
          <div className="p-5 space-y-4">
            <p className="text-sm text-slate-600">{t("mapping.intro")}</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3 max-w-3xl">{inSight.map(mappingField)}</div>
            {foldedFields.length ? (
              <details className="max-w-3xl rounded-md border border-slate-200">
                <summary className="cursor-pointer px-3 py-2 text-sm text-slate-600">{t("mapping.folded", { count: foldedFields.length })}</summary>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3 border-t border-slate-200 p-3">{foldedFields.map(mappingField)}</div>
              </details>
            ) : null}
            {unread.length ? <p className="max-w-3xl text-sm text-slate-600">{t("mapping.unread", { count: unread.length, columns: unread.join(", ") })}</p> : null}
            {job.kind === "COSTS" ? (
              <div className="max-w-xl">
                <label htmlFor="default-cost-type" className={label}>{t("mapping.defaultType")}</label>
                <select id="default-cost-type" value={defaultCostType} onChange={(e) => setDefaultCostType(e.target.value as CostType | "")} aria-describedby="default-cost-type-hint" className={input}>
                  <option value="">{t("mapping.defaultTypeNone")}</option>
                  {COST_TYPES.map((c) => <option key={c} value={c}>{costTypeLabel(c)}</option>)}
                </select>
                <p id="default-cost-type-hint" className="mt-1 text-xs text-slate-500">{t("mapping.defaultTypeHint")}</p>
              </div>
            ) : null}
            {missingRequired.length ? <p className="text-sm text-amber-700">{t("mapping.required", { fields: missingRequired.join(", ") })}</p> : null}
            {missingOneOf.map((group) => (
              <p key={group.join()} className="text-sm text-amber-700">{t("mapping.oneOf", { count: group.length, fields: group.join(", ") })}</p>
            ))}
            {mappingError ? <p role="alert" className="text-sm text-red-700">{mappingError}</p> : null}
            <div className="flex gap-2">
              <Link href="/imports" className={btnSecondary}>{t("mapping.back")}</Link>
              <button type="button" onClick={() => validate()} disabled={pending || missingRequired.length > 0 || missingOneOf.length > 0} className={btnPrimary}>
                {pending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" aria-hidden /> : null}{t("mapping.validate")}
              </button>
            </div>
          </div>
        </Card>
      ) : null}

      {step === "review" ? (
        <Card title={t("review.card")} right={<span className="text-xs text-slate-500">{t("review.nothingWritten")}</span>}>
          <div className="p-5 space-y-5">
            {changed ? (
              <div role="alert" className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950">
                {t("review.changed", { before: changedFigure(changed.before), after: changedFigure(changed.after) })}
              </div>
            ) : null}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
              {figures(report).map(([k, v]) => (
                <div key={k} className="bg-slate-50 rounded-md px-3 py-2"><div className="text-xs text-slate-500">{k}</div><div className="font-medium tabular-nums">{v}</div></div>
              ))}
            </div>
            {/* What the reader decided about the file itself, before any row: a header on
                line 3 or a skipped totals row used to look like lost rows. */}
            {report.header_row > 1 ? <p className="text-xs text-slate-500">{t("review.headerRow", { line: report.header_row })}</p> : null}
            {report.totals_row_ignored ? <p className="text-xs text-slate-500">{t("review.totalsRowIgnored")}</p> : null}
            {report.forward_filled_rows ? <p className="text-xs text-slate-500">{t("review.forwardFilled", { count: report.forward_filled_rows })}</p> : null}
            {job.kind === "COSTS" ? <CostsPreview report={report} baseCurrency={baseCurrency} labelTypes={labelTypes} pending={pending} onRetype={(types) => validate({ labelTypes: types })} /> : null}
            {job.kind === "COSTS" && forceDuplicates ? (
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950">
                <span>{t("issues.forced")}</span>
                <button type="button" onClick={() => validate({ forceDuplicates: false })} disabled={pending} className="text-sm font-medium text-blue-700 underline underline-offset-2 hover:no-underline">{t("issues.unforce")}</button>
              </div>
            ) : null}
            {errors.length ? (
              <IssueGroups
                title={[
                  t("review.errorSummary", { rows: leftOut, total: report.row_count, errors: errors.length }),
                  leftWithoutError ? t("review.leftWithoutError", { count: leftWithoutError, kind: job.kind }) : "",
                ].join(" ").trim()}
                issues={errors}
                tone="red"
                kind={job.kind}
                fieldName={fieldName}
                baseCurrency={baseCurrency}
                actions={{
                  DUPLICATE_COST: (
                    <button type="button" onClick={() => validate({ forceDuplicates: true })} disabled={pending} className={btnSecondary}>{t("issues.forceDuplicates")}</button>
                  ),
                }}
              />
            ) : (
              <p className="text-sm text-emerald-700">{t("review.noError")}</p>
            )}
            {warnings.length ? <IssueGroups title={t("review.warningCount", { count: warnings.length })} issues={warnings} tone="amber" kind={job.kind} fieldName={fieldName} baseCurrency={baseCurrency} /> : null}
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" onClick={() => setStep("mapping")} className={btnSecondary}>{t("review.backToMapping")}</button>
              <button type="button" onClick={() => commit("skip_rows")} disabled={pending || report.valid_rows === 0} className={btnPrimary}>
                {pending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" aria-hidden /> : null}{errors.length ? t("review.importValid") : t("review.import")}
              </button>
              {errors.length ? <span className="text-xs text-slate-500">{t("review.orFix")}</span> : null}
            </div>
            {/* The columns step is skipped for a file that reads itself: what was read stays said, one click from being changed. */}
            <p className="text-xs text-slate-500">
              {t("review.columnsRead", { read: job.columns.length - unread.length, total: job.columns.length })}
              {unread.length ? ` ${t("review.columnsUnread", { count: unread.length, columns: unread.join(", ") })}` : null}
            </p>
          </div>
        </Card>
      ) : null}

      {step === "done" ? (
        <>
          <Card title={t("done.card")}>
            <ImportDone job={job} baseCurrency={baseCurrency} />
          </Card>
          <ImportSteps kinds={kinds} states={states} />
        </>
      ) : null}
    </div>
  );
}
