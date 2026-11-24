"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Check, Download, Loader2, Upload } from "lucide-react";
import { Card, btnPrimary, btnSecondary } from "@/components/layout/AppShell";
import FileTooLarge from "@/components/shared/FileTooLarge";
import { dropImport } from "@/features/actions";
import { downloadImportTemplate } from "@/features/imports/importTemplate";
import type { ImportStepState } from "@/features/imports/stepStates";
import type { Schemas } from "@/lib/api/client";
import type { ImportKind } from "@/lib/domain";
import { MAX_UPLOAD_BYTES } from "@/lib/uploads";

type KindInfo = Schemas["ImportKindInfo"];
/** What went wrong with the file a step was given, said in that step. */
type Refusal = { kind: ImportKind; tooLarge?: File; error?: string; existingId?: string };

const LEGACY: ImportKind = "LEGACY_PO_CONTAINER";

/**
 * The files of a quarter as numbered steps, in the order the API gives them — the order they build on
 * each other: the price list lends its duty rates only to order lines written after it, costs land on
 * the boxes and orders already there. Each step is its own drop zone: the file dropped there is that
 * step's file, with no kind to choose, and is read at once. A step says where it stands — the last
 * file of its kind that went in, or one still waiting — and the first one with nothing in is the
 * current one. The old one-row-per-order format stays reachable, folded away.
 */
export default function ImportSteps({ kinds, states, current = null }: { kinds: KindInfo[]; states: Partial<Record<ImportKind, ImportStepState>>; current?: ImportKind | null }) {
  const t = useTranslations("importWizard");
  const locale = useLocale();
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [sent, setSent] = useState<{ kind: ImportKind; name: string } | null>(null);
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const [over, setOver] = useState<ImportKind | null>(null);
  const main = kinds.filter((k) => k.kind !== LEGACY);
  const legacy = kinds.find((k) => k.kind === LEGACY);
  const next = current ?? main.find((k) => !states[k.kind]?.done)?.kind ?? null;
  const reading = pending ? sent : null;
  const allDone = main.length > 0 && main.every((k) => states[k.kind]?.done);

  const send = (kind: ImportKind, file: File | undefined) => {
    setOver(null);
    if (!file || pending) return;
    // Not `isTooLarge(file)`: a type guard that answers no would leave `file` typed as nothing.
    if (file.size > MAX_UPLOAD_BYTES) return void setRefusal({ kind, tooLarge: file });
    setRefusal(null);
    setSent({ kind, name: file.name });
    const fd = new FormData();
    fd.append("file", file);
    fd.append("kind", kind);
    startTransition(async () => {
      // Refused before the action runs (connection dropped, a body over a limit): it rejects.
      const result = await dropImport(fd).catch(() => null);
      if (!result) return void setRefusal({ kind, error: t("upload.failed") });
      if (!result.ok) return void setRefusal({ kind, error: result.error, existingId: result.existingId });
      router.push(`/imports/new?job=${result.id}`);
    });
  };

  const step = (k: KindInfo, n: number | null) => {
    const state = states[k.kind];
    const isNext = k.kind === next;
    const busy = reading?.kind === k.kind;
    const refused = refusal?.kind === k.kind ? refusal : null;
    const title = t(`kinds.${k.kind}.title`);
    const errorId = `import-refused-${k.kind}`;
    return (
      <li key={k.kind} id={`step-${k.kind}`} aria-current={isNext ? "step" : undefined} className={`scroll-mt-24 flex flex-col gap-4 px-5 py-5 md:flex-row md:items-start md:gap-6 ${isNext ? "bg-blue-50/50" : ""}`}>
        <div className="flex min-w-0 flex-1 gap-3">
          {n === null ? null : (
            <span
              aria-hidden
              className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold tabular-nums ${
                state?.done ? "bg-emerald-600 text-white" : isNext ? "bg-slate-900 text-white" : "border border-slate-300 bg-white text-slate-600"
              }`}
            >
              {state?.done ? <Check className="h-4 w-4" /> : n}
            </span>
          )}
          <div className="min-w-0">
            <h3 className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm font-semibold text-slate-900">
              {n === null ? title : t("stepList.step", { n, title })}
              {isNext && !state?.done ? <span className="rounded-md bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800">{t("stepList.now")}</span> : null}
            </h3>
            <p className="mt-1 text-sm text-slate-700">{t(`kinds.${k.kind}.brings`)}</p>
            <p className="mt-1 text-xs text-slate-500">{t(`kinds.${k.kind}.where`)}</p>
            {state?.done ? (
              <p className="mt-2 text-sm text-emerald-800">
                <span className="font-medium">{t("stepList.done")}</span> {t("stepList.doneLine", { file: state.done.file, date: state.done.date, result: state.done.result })}
              </p>
            ) : null}
            {state?.waiting ? (
              <p className="mt-2 text-sm text-amber-800">
                {t("stepList.waiting", { file: state.waiting.file })}{" "}
                <Link href={`/imports/new?job=${state.waiting.id}`} className="font-medium underline underline-offset-2 hover:no-underline">{t("stepList.resume")}</Link>
              </p>
            ) : null}
            <button
              type="button"
              onClick={() => downloadImportTemplate(k, locale)}
              aria-label={t("kinds.templateFor", { kind: title })}
              className="mt-2 inline-flex items-center gap-1.5 text-xs text-blue-700 underline underline-offset-2 hover:no-underline"
            >
              <Download className="h-3.5 w-3.5" aria-hidden />
              {t("kinds.template")}
            </button>
          </div>
        </div>
        <div className="shrink-0 space-y-2 md:w-72">
          <label
            onDragEnter={() => setOver(k.kind)}
            onDragLeave={() => setOver((o) => (o === k.kind ? null : o))}
            className={`relative flex min-h-24 flex-col items-center justify-center rounded-md border-2 border-dashed px-4 py-4 text-center has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-blue-500 ${
              pending ? "cursor-progress opacity-70" : "cursor-pointer"
            } ${over === k.kind ? "border-blue-500 bg-blue-50" : isNext ? "border-blue-400 bg-white hover:bg-blue-50/60" : "border-slate-300 bg-white hover:bg-slate-50"}`}
          >
            <input
              type="file"
              accept=".csv,.xlsx,text/csv"
              disabled={pending}
              onChange={(e) => {
                const file = e.target.files?.[0];
                // The same file can be dropped again after a correction: the field forgets it.
                e.target.value = "";
                send(k.kind, file);
              }}
              className="absolute inset-0 h-full w-full cursor-pointer opacity-0 disabled:cursor-progress"
              aria-label={t("upload.chooseFor", { kind: title })}
              aria-invalid={refused ? true : undefined}
              aria-describedby={refused ? errorId : undefined}
            />
            {busy ? (
              <>
                <Loader2 className="mb-1.5 h-5 w-5 animate-spin text-slate-500" aria-hidden />
                <p role="status" className="break-all text-sm text-slate-700">{t("stepList.reading", { file: reading?.name ?? "" })}</p>
              </>
            ) : (
              <>
                <Upload className={`mb-1.5 h-5 w-5 ${isNext ? "text-blue-600" : "text-slate-400"}`} aria-hidden />
                <p className="text-sm font-medium text-slate-800">{t(state?.done ? "stepList.dropAgain" : "stepList.drop")}</p>
                <p className="mt-0.5 text-xs text-slate-500">{t("stepList.formats")}</p>
              </>
            )}
          </label>
          {refused?.tooLarge ? <FileTooLarge id={errorId} file={refused.tooLarge} kind="import" /> : null}
          {refused?.existingId ? (
            <p id={errorId} role="alert" className="text-sm text-amber-900">
              {t("upload.alreadyImported")}{" "}
              <Link href={`/imports#import-${refused.existingId}`} className="text-blue-700 underline underline-offset-2 hover:no-underline">{t("upload.openExisting")}</Link>
            </p>
          ) : refused?.error ? (
            <p id={errorId} role="alert" className="text-sm text-red-700">{refused.error}</p>
          ) : null}
        </div>
      </li>
    );
  };

  return (
    <Card title={t("stepList.title")}>
      <p className="border-b border-slate-200 px-5 py-3 text-sm text-slate-600">{t("stepList.intro")}</p>
      <ol className="divide-y divide-slate-200">{main.map((k, i) => step(k, i + 1))}</ol>
      {allDone ? (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-slate-200 bg-emerald-50/60 px-5 py-4">
          <p className="text-sm font-medium text-emerald-900">{t("stepList.allDone")}</p>
          <Link href="/cost-audit" className={btnPrimary}>{t("stepList.openAudit")}</Link>
          <Link href="/containers" className={btnSecondary}>{t("stepList.seeContainers")}</Link>
        </div>
      ) : null}
      <p className="border-t border-slate-200 px-5 py-3 text-xs text-slate-500">{t("stepList.hint")}</p>
      {legacy ? (
        <details className="border-t border-slate-200" open={next === LEGACY || Boolean(states[LEGACY]?.waiting) || refusal?.kind === LEGACY || undefined}>
          <summary className="cursor-pointer px-5 py-3 text-xs text-slate-600">{t("kinds.other")}</summary>
          <ul>{step(legacy, null)}</ul>
        </details>
      ) : null}
    </Card>
  );
}
