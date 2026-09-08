"use client";

import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, FileType, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Card, btnPrimary, btnSecondary, input, label, td, th } from "@/components/layout/AppShell";
import { commitImport, createImport, validateImport } from "@/features/actions";
import type { ImportJobResponse } from "@/lib/api/client";
import { IMPORT_FIELDS, type ImportKind } from "@/lib/domain";

type Step = "upload" | "mapping" | "review" | "done";

const STEPS: { id: Step; label: string }[] = [
  { id: "upload", label: "1. Upload" },
  { id: "mapping", label: "2. Map columns" },
  { id: "review", label: "3. Validation report" },
  { id: "done", label: "4. Done" },
];

type Issue = { row: number; field: string; code: string; message: string };

export default function ImportWizard({ initialJob }: { initialJob: ImportJobResponse | null }) {
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
  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const missingRequired = useMemo(() => fields.filter((f) => f.required && !mapping[f.field]).map((f) => f.label), [fields, mapping]);

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
      toast.success("Import committed. Allocations recalculated.");
      router.refresh();
    });
  };

  return (
    <div className="space-y-6">
      <ol className="flex flex-wrap gap-2 text-xs">
        {STEPS.map((s) => (
          <li key={s.id} className={`px-3 py-1.5 rounded-md border ${s.id === step ? "bg-slate-900 text-white border-slate-900" : "bg-white text-slate-500 border-slate-200"}`}>{s.label}</li>
        ))}
      </ol>

      {step === "upload" ? (
        <Card title="Choose a file">
          <div className="p-5 space-y-4 max-w-xl">
            <div>
              <label className={label} htmlFor="kind">Format</label>
              <select id="kind" value={kind} onChange={(e) => setKind(e.target.value as ImportKind)} className={input}>
                <option value="PURCHASE_ORDERS">One row per purchase-order line (SKU, quantity, unit price, optional container)</option>
                <option value="LEGACY_PO_CONTAINER">One row per purchase order with a total value and a container</option>
              </select>
            </div>
            <label className="relative border-2 border-dashed border-slate-300 rounded-md p-8 flex flex-col items-center justify-center text-center hover:bg-slate-50 cursor-pointer">
              <input type="file" accept=".csv,.xlsx,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" aria-label="Choose a file" />
              {file ? (
                <><CheckCircle2 className="w-8 h-8 text-emerald-500 mb-2" /><p className="text-sm font-medium">{file.name}</p><p className="text-xs text-slate-500 mt-1">{(file.size / 1024).toFixed(1)} KB</p></>
              ) : (
                <><FileType className="w-8 h-8 text-slate-400 mb-2" /><p className="text-sm font-medium text-slate-700">Click to choose a CSV or XLSX</p><p className="text-xs text-slate-500 mt-1">Excel FR exports (BOM, semicolons, French decimals) are fine.</p></>
              )}
            </label>
            <button type="button" onClick={upload} disabled={!file || pending} className={btnPrimary}>
              {pending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}Upload and detect columns
            </button>
          </div>
        </Card>
      ) : null}

      {step === "mapping" && job ? (
        <Card title={`Map the columns of ${job.original_filename ?? "the file"}`} right={<span className="text-xs text-slate-500">{plural(job.row_count, "row")} · {job.encoding}{job.delimiter ? ` · "${job.delimiter}"` : ""}</span>}>
          <div className="p-5 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3 max-w-3xl">
              {fields.map((f) => (
                <div key={f.field} className="flex items-center gap-3">
                  <label htmlFor={`map-${f.field}`} className="w-44 text-sm text-slate-700 shrink-0">{f.label}{f.required ? <span className="text-red-500"> *</span> : null}</label>
                  <select id={`map-${f.field}`} value={mapping[f.field] ?? ""} onChange={(e) => setMapping((m) => { const n = { ...m }; if (e.target.value) n[f.field] = e.target.value; else delete n[f.field]; return n; })} className={input}>
                    <option value="">— not in file —</option>
                    {job.columns.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
              ))}
            </div>
            {missingRequired.length ? <p className="text-sm text-amber-700">Required: {missingRequired.join(", ")}</p> : null}
            <div className="flex gap-2">
              <button type="button" onClick={() => setStep("upload")} className={btnSecondary}>Back</button>
              <button type="button" onClick={validate} disabled={pending || missingRequired.length > 0} className={btnPrimary}>
                {pending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}Validate (dry run)
              </button>
            </div>
          </div>
        </Card>
      ) : null}

      {step === "review" && job ? (
        <Card title="What the import will do" right={<span className="text-xs text-slate-500">nothing written yet</span>}>
          <div className="p-5 space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
              {[
                ["Valid rows", `${report.valid_rows ?? 0} / ${report.row_count ?? job.row_count}`],
                ["Purchase orders", `${report.purchase_orders_created ?? 0} new, ${report.purchase_orders_updated ?? 0} updated`],
                ["Lines", `${report.lines_created ?? 0} new, ${report.lines_updated ?? 0} updated`],
                ["Containers / loads", `${report.containers_created ?? 0} / ${(report.loads_created as number ?? 0) + (report.loads_updated as number ?? 0)}`],
              ].map(([k, v]) => (
                <div key={k} className="bg-slate-50 rounded-md px-3 py-2"><div className="text-xs text-slate-500">{k}</div><div className="font-medium">{v}</div></div>
              ))}
            </div>
            {warnings.length ? <IssueTable title={plural(warnings.length, "warning")} issues={warnings} tone="amber" /> : null}
            {errors.length ? <IssueTable title={`${plural(errorRows, "row")} with ${plural(errors.length, "error")} will be skipped`} issues={errors} tone="red" /> : <p className="text-sm text-emerald-700">No row error.</p>}
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => setStep("mapping")} className={btnSecondary}>Back to mapping</button>
              <button type="button" onClick={() => commit("skip_rows")} disabled={pending} className={btnPrimary}>
                {pending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}{errors.length ? "Import valid rows" : "Import"}
              </button>
              {errors.length ? <span className="text-xs text-slate-500 self-center">or fix the file and upload again</span> : null}
            </div>
          </div>
        </Card>
      ) : null}

      {step === "done" && job ? (
        <Card title="Import committed">
          <div className="p-5 space-y-3 text-sm">
            <p>{plural(report.purchase_orders_created as number ?? 0, "purchase order")}, {plural(report.lines_created as number ?? 0, "line")}, {plural(report.containers_created as number ?? 0, "container")} and {plural(report.loads_created as number ?? 0, "load")} created.{errorRows ? ` ${plural(errorRows, "row")} skipped.` : ""}</p>
            <div className="flex gap-2">
              <button type="button" onClick={() => router.push("/")} className={btnPrimary}>Go to containers</button>
              <button type="button" onClick={() => { setJob(null); setFile(null); setMapping({}); setStep("upload"); }} className={btnSecondary}>Import another file</button>
            </div>
          </div>
        </Card>
      ) : null}
    </div>
  );
}

function IssueTable({ title, issues, tone }: { title: string; issues: Issue[]; tone: "amber" | "red" }) {
  const color = tone === "amber" ? "text-amber-700" : "text-red-700";
  return (
    <div>
      <div className={`text-sm font-medium mb-2 ${color}`}>{title}</div>
      <div className="overflow-x-auto border border-slate-200 rounded-md max-h-64 overflow-y-auto">
        <table className="min-w-full divide-y divide-slate-200 text-xs">
          <thead className="bg-slate-50"><tr><th className={th}>Row</th><th className={th}>Field</th><th className={th}>Code</th><th className={th}>Message</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {issues.slice(0, 200).map((i, idx) => (
              <tr key={idx}><td className={td}>{i.row}</td><td className={`${td} font-mono`}>{i.field}</td><td className={`${td} font-mono`}>{i.code}</td><td className="px-4 py-2">{i.message}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
