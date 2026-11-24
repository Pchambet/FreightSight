import type { Metadata } from "next";
import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { Card, PageHeader, td, tdRight, th, thRight } from "@/components/layout/AppShell";
import ApiErrorNotice from "@/components/shared/ApiErrorNotice";
import ScrollRegion from "@/components/shared/ScrollRegion";
import ImportSteps from "@/features/imports/ImportSteps";
import DeleteImportButton from "@/features/imports/DeleteImportButton";
import { deleteTarget } from "@/features/imports/deleteTarget";
import { importResultLine, importStepStates } from "@/features/imports/stepStates";
import AuditPreparation from "@/features/report/AuditPreparation";
import { presetRange } from "@/features/report/auditPeriods";
import { api } from "@/lib/api/client";
import { dateShort } from "@/lib/format";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("imports");
  return { title: t("title") };
}

const STATUS_STYLE: Record<string, string> = {
  PARSED: "bg-slate-100 text-slate-700",
  VALIDATED: "bg-blue-50 text-blue-700",
  DONE: "bg-emerald-50 text-emerald-700",
  FAILED: "bg-red-50 text-red-700",
};

export default async function ImportsPage() {
  const [{ data }, kindsRes, t, tc, locale, org] = await Promise.all([
    api.GET("/api/v1/imports"),
    api.GET("/api/v1/imports/kinds"),
    getTranslations("imports"),
    getTranslations("common"),
    getLocale(),
    api.GET("/api/v1/organization"),
  ]);
  const jobs = data ?? [];
  const kinds = kindsRes.data ?? [];
  const base = org.data?.base_currency ?? "EUR";
  const states = await importStepStates(jobs, base);
  const quarter = presetRange("lastQuarter");
  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      {/* The page is the steps: each file is dropped on its own, in order, and says where it stands. */}
      {kinds.length ? <div className="mb-6"><ImportSteps kinds={kinds} states={states} /></div> : <ApiErrorNotice error={kindsRes.error} retryHref="/imports" />}
      <AuditPreparation periodFrom={quarter.from} periodTo={quarter.to} showPeriod />
      <Card title={t("history")}>
        <ScrollRegion label={t("history")}>
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50"><tr><th className={th}>{t("th.date")}</th><th className={th}>{t("th.file")}</th><th className={th}>{t("th.kind")}</th><th className={th}>{t("th.status")}</th><th className={thRight}>{t("th.rows")}</th><th className={thRight}>{t("th.errors")}</th><th className={th}>{t("th.result")}</th><th className="sticky right-0 w-px bg-slate-50 px-2"><span className="sr-only">{t("th.actions")}</span></th></tr></thead>
            <tbody className="divide-y divide-slate-200">
              {jobs.length === 0 ? (
                <tr><td colSpan={8} className="px-5 py-10 text-center text-sm text-slate-500">{t("empty")}</td></tr>
              ) : (
                jobs.map((j) => {
                  const target = deleteTarget(j);
                  return (
                  // The anchor a « file already imported » refusal leads to.
                  <tr key={j.id} id={`import-${j.id}`} className="scroll-mt-24 target:bg-amber-50">
                    <td className={`${td} text-slate-600`}>{dateShort(j.created_at, locale)}</td>
                    {/* An ERP-synced job has no uploaded file: its synthetic name is not shown as one. */}
                    <td className={td}>{j.source === "erp_sync" ? t("source.erp_sync") : (j.original_filename ?? tc("empty"))}</td>
                    <td className={`${td} text-xs text-slate-600`}>{t(`kind.${j.kind}`)}</td>
                    <td className={td}>
                      {j.undone_at ? (
                        <span className="inline-flex rounded-md px-2 py-0.5 text-xs font-medium bg-slate-100 text-slate-600">{t("undoneOn", { date: dateShort(j.undone_at, locale) })}</span>
                      ) : (
                        <span className={`inline-flex rounded-md px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[j.status]}`}>{t(`status.${j.status}`)}</span>
                      )}
                    </td>
                    <td className={tdRight}>{j.row_count}</td>
                    <td className={`${tdRight} ${j.error_count ? "text-amber-700" : ""}`}>{j.error_count}</td>
                    <td className={`${td} min-w-48 max-w-72 whitespace-normal text-xs text-slate-600`}>
                      {j.status === "DONE"
                        ? importResultLine(j, t, base, locale)
                        : j.status === "PARSED" || j.status === "VALIDATED"
                          ? <Link href={`/imports/new?job=${j.id}`} className="text-blue-600 hover:underline">{t("continue")}</Link>
                          : tc("empty")}
                    </td>
                    {/* Held at the right edge: on a table wider than its room the bin stays in sight. */}
                    <td className="sticky right-0 w-px bg-white px-2 py-1 text-right">{target ? <DeleteImportButton target={target} /> : null}</td>
                  </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </ScrollRegion>
      </Card>
    </>
  );
}
