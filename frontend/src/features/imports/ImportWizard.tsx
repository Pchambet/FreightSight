"use client";

import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { CheckCircle2, FileType, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Card, btnPrimary, btnSecondary, input, label, td, th } from "@/components/layout/AppShell";
import { commitImport, createImport, validateImport } from "@/features/actions";
import type { ImportJobResponse } from "@/lib/api/client";
import { IMPORT_FIELDS, type ImportKind } from "@/lib/domain";

type Step = "upload" | "mapping" | "review" | "done";

const STEPS: Step[] = ["upload", "mapping", "review", "done"];

type Issue = { row: number; field: string; code: string; message: string };

export default function ImportWizard({ initialJob }: { initialJob: ImportJobResponse | null }) {
  const t = useTranslations("importWizard");
  const fieldLabel = useTranslations("domain.importField");
  const [job, setJob] = useState<ImportJobResponse | null>(initialJob);
  const [step, setStep] = useState<Step>(initialJob ? "mapping" : "upload");
  const [kind, setKind] = useState<ImportKind>(initialJob?.kind ?? "PURCHASE_ORDERS");
  const [file, setFile] = useState<File | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>(initialJob?.mapping ?? {});
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  const fields = IMPORT_FIELDS[kind];
  const report = (job?.report ?? {}) as Record<string, unknown>;
  const errors = (report.errors as Issue[] | undefined) ?? [];
  const warnings = (report.warnings as Issue[] | undefined) ?? [];
  const errorRows = new Set(errors.map((e) => e.row)).size;
  const missingRequired = useMemo(
    () => fields.filter((f) => f.required && !mapping[f.field]).map((f) => fieldLabel(f.field)),
    [fields, mapping, fieldLabel],
  );

  const upload = () => {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("kind", kind);
    startTransition(async () => {
      const result = await createImport(fd);
      if (!result.ok) return void toast.error(result.error);
      setJob(result.data);
      setMapping(result.data.mapping);
      setStep("mapping");
    });
  };

  const validate = () => {
    if (!job) return;
    startTransition(async () => {
      const result = await validateImport(job.id, mapping);
      if (!result.ok) return void toast.error(result.error);
      setJob(result.data);
      setStep("review");
    });
  };

  const commit = (onError: "skip_rows" | "abort") => {
    if (!job) return;
    startTransition(async () => {
      const result = await commitImport(job.id, onError);
      if (!result.ok) return void toast.error(result.error);
      setJob(result.data);
      setStep("done");
      toast.success(t("done.committed"));
      router.refresh();
    });
  };

  return (
    <div className="space-y-6">
      <ol className="flex flex-wrap gap-2 text-xs">
        {STEPS.map((s) => (
          <li key={s} className={`px-3 py-1.5 rounded-md border ${s === step ? "bg-slate-900 text-white border-slate-900" : "bg-white text-slate-500 border-slate-200"}`}>{t(`steps.${s}`)}</li>
        ))}
      </ol>

      {step === "upload" ? (
        <Card title={t("upload.card")}>
          <div className="p-5 space-y-4 max-w-xl">
            <div>
              <label className={label} htmlFor="kind">{t("upload.format")}</label>
              <select id="kind" value={kind} onChange={(e) => setKind(e.target.value as ImportKind)} className={input}>
                <option value="PURCHASE_ORDERS">{t("upload.kindPurchaseOrders")}</option>
                <option value="LEGACY_PO_CONTAINER">{t("upload.kindLegacy")}</option>
              </select>
            </div>
            <label className="relative border-2 border-dashed border-slate-300 rounded-md p-8 flex flex-col items-center justify-center text-center hover:bg-slate-50 cursor-pointer">
              <input type="file" accept=".csv,.xlsx,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" aria-label={t("upload.choose")} />
              {file ? (
                <><CheckCircle2 className="w-8 h-8 text-emerald-500 mb-2" /><p className="text-sm font-medium">{file.name}</p><p className="text-xs text-slate-500 mt-1">{(file.size / 1024).toFixed(1)} KB</p></>
              ) : (
                <><FileType className="w-8 h-8 text-slate-400 mb-2" /><p className="text-sm font-medium text-slate-700">{t("upload.cta")}</p><p className="text-xs text-slate-500 mt-1">{t("upload.hint")}</p></>
              )}
            </label>
            <button type="button" onClick={upload} disabled={!file || pending} className={btnPrimary}>
              {pending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}{t("upload.submit")}
            </button>
          </div>
        </Card>
      ) : null}

      {step === "mapping" && job ? (
        <Card title={t("mapping.card", { filename: job.original_filename ?? t("mapping.fallbackFilename") })} right={<span className="text-xs text-slate-500">{t("mapping.meta", { rows: job.row_count, encoding: job.encoding ?? "" })}{job.delimiter ? ` · "${job.delimiter}"` : ""}</span>}>
          <div className="p-5 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3 max-w-3xl">
              {fields.map((f) => (
                <div key={f.field} className="flex items-center gap-3">
                  <label htmlFor={`map-${f.field}`} className="w-44 text-sm text-slate-700 shrink-0">{fieldLabel(f.field)}{f.required ? <span className="text-red-500"> *</span> : null}</label>
                  <select id={`map-${f.field}`} value={mapping[f.field] ?? ""} onChange={(e) => setMapping((m) => { const n = { ...m }; if (e.target.value) n[f.field] = e.target.value; else delete n[f.field]; return n; })} className={input}>
                    <option value="">{t("mapping.notInFile")}</option>
                    {job.columns.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
              ))}
            </div>
            {missingRequired.length ? <p className="text-sm text-amber-700">{t("mapping.required", { fields: missingRequired.join(", ") })}</p> : null}
            <div className="flex gap-2">
              <button type="button" onClick={() => setStep("upload")} className={btnSecondary}>{t("mapping.back")}</button>
              <button type="button" onClick={validate} disabled={pending || missingRequired.length > 0} className={btnPrimary}>
                {pending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}{t("mapping.validate")}
              </button>
            </div>
          </div>
        </Card>
      ) : null}

      {step === "review" && job ? (
        <Card title={t("review.card")} right={<span className="text-xs text-slate-500">{t("review.nothingWritten")}</span>}>
          <div className="p-5 space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
              {[
                [t("review.validRows"), `${report.valid_rows ?? 0} / ${report.row_count ?? job.row_count}`],
                [t("review.purchaseOrders"), t("review.newUpdated", { created: (report.purchase_orders_created as number) ?? 0, updated: (report.purchase_orders_updated as number) ?? 0 })],
                [t("review.lines"), t("review.newUpdated", { created: (report.lines_created as number) ?? 0, updated: (report.lines_updated as number) ?? 0 })],
                [t("review.containersLoads"), `${report.containers_created ?? 0} / ${((report.loads_created as number) ?? 0) + ((report.loads_updated as number) ?? 0)}`],
              ].map(([k, v]) => (
                <div key={k} className="bg-slate-50 rounded-md px-3 py-2"><div className="text-xs text-slate-500">{k}</div><div className="font-medium">{v}</div></div>
              ))}
            </div>
            {warnings.length ? <IssueTable title={t("review.warningCount", { count: warnings.length })} issues={warnings} tone="amber" /> : null}
            {errors.length ? <IssueTable title={t("review.errorSummary", { rows: errorRows, errors: errors.length })} issues={errors} tone="red" /> : <p className="text-sm text-emerald-700">{t("review.noError")}</p>}
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => setStep("mapping")} className={btnSecondary}>{t("review.backToMapping")}</button>
              <button type="button" onClick={() => commit("skip_rows")} disabled={pending} className={btnPrimary}>
                {pending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}{errors.length ? t("review.importValid") : t("review.import")}
              </button>
              {errors.length ? <span className="text-xs text-slate-500 self-center">{t("review.orFix")}</span> : null}
            </div>
          </div>
        </Card>
      ) : null}

      {step === "done" && job ? (
        <Card title={t("done.card")}>
          <div className="p-5 space-y-3 text-sm">
            <p>
              {t("done.summary", {
                pos: (report.purchase_orders_created as number) ?? 0,
                lines: (report.lines_created as number) ?? 0,
                containers: (report.containers_created as number) ?? 0,
                loads: (report.loads_created as number) ?? 0,
              })}
              {errorRows ? ` ${t("done.skipped", { rows: errorRows })}` : ""}
            </p>
            <div className="flex gap-2">
              <button type="button" onClick={() => router.push("/containers")} className={btnPrimary}>{t("done.goToContainers")}</button>
              <button type="button" onClick={() => { setJob(null); setFile(null); setMapping({}); setStep("upload"); }} className={btnSecondary}>{t("done.another")}</button>
            </div>
          </div>
        </Card>
      ) : null}
    </div>
  );
}

function IssueTable({ title, issues, tone }: { title: string; issues: Issue[]; tone: "amber" | "red" }) {
  const t = useTranslations("importWizard.review.th");
  const errorCode = useTranslations("errors");
  const color = tone === "amber" ? "text-amber-700" : "text-red-700";
  return (
    <div>
      <div className={`text-sm font-medium mb-2 ${color}`}>{title}</div>
      <div className="overflow-x-auto border border-slate-200 rounded-md max-h-64 overflow-y-auto">
        <table className="min-w-full divide-y divide-slate-200 text-xs">
          <thead className="bg-slate-50"><tr><th className={th}>{t("row")}</th><th className={th}>{t("field")}</th><th className={th}>{t("code")}</th><th className={th}>{t("message")}</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {issues.slice(0, 200).map((i, idx) => (
              <tr key={idx}><td className={td}>{i.row}</td><td className={`${td} font-mono`}>{i.field}</td><td className={`${td} font-mono`}>{i.code}</td><td className="px-4 py-2">{errorCode.has(i.code) ? errorCode(i.code) : i.message}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
