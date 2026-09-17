import type { Metadata } from "next";
import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { Card, PageHeader, btnPrimary, td, tdRight, th, thRight } from "@/components/layout/AppShell";
import WorkflowNextStep from "@/features/workflow/WorkflowNextStep";
import { importsHubStep } from "@/features/workflow/steps";
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
  const [{ data }, t, tc, locale] = await Promise.all([
    api.GET("/api/v1/imports"),
    getTranslations("imports"),
    getTranslations("common"),
    getLocale(),
  ]);
  const jobs = data ?? [];
  const hubStep = importsHubStep(jobs);
  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} actions={<Link href="/imports/new" className={btnPrimary}>{t("new")}</Link>} />
      <WorkflowNextStep step={hubStep} />
      <Card>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50"><tr><th className={th}>{t("th.date")}</th><th className={th}>{t("th.file")}</th><th className={th}>{t("th.kind")}</th><th className={th}>{t("th.status")}</th><th className={thRight}>{t("th.rows")}</th><th className={thRight}>{t("th.errors")}</th><th className={th}>{t("th.result")}</th></tr></thead>
            <tbody className="divide-y divide-slate-200">
              {jobs.length === 0 ? (
                <tr><td colSpan={7} className="px-5 py-14 text-center text-sm text-slate-500">{t("empty")} <Link href="/imports/new" className="text-blue-600 hover:underline font-medium">{t("emptyLink")}</Link> {t("emptySuffix")}</td></tr>
              ) : (
                jobs.map((j) => {
                  const r = j.report as Record<string, number | undefined>;
                  // `source` (upload | erp_sync) is not in the generated schema yet (needs_other_lane)
                  // — an ERP-synced job has no uploaded file, and used to show its synthetic filename
                  // ("odoo-sync.csv") as if someone had dropped it by hand (audit B23).
                  const source = (j as { source?: "upload" | "erp_sync" }).source;
                  return (
                    <tr key={j.id}>
                      <td className={`${td} text-slate-600`}>{dateShort(j.created_at, locale)}</td>
                      <td className={td}>{source === "erp_sync" ? t("source.erp_sync") : (j.original_filename ?? tc("empty"))}</td>
                      <td className={`${td} text-xs text-slate-600`}>{t(`kind.${j.kind}`)}</td>
                      <td className={td}><span className={`inline-flex rounded-md px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[j.status]}`}>{t(`status.${j.status}`)}</span></td>
                      <td className={tdRight}>{j.row_count}</td>
                      <td className={`${tdRight} ${j.error_count ? "text-amber-700" : ""}`}>{j.error_count}</td>
                      <td className={`${td} text-xs text-slate-600`}>
                        {j.status === "DONE"
                          ? t("result", { pos: r.purchase_orders_created ?? 0, lines: r.lines_created ?? 0, containers: r.containers_created ?? 0, loads: r.loads_created ?? 0 })
                          : j.status === "PARSED" || j.status === "VALIDATED"
                            ? <Link href={`/imports/new?job=${j.id}`} className="text-blue-600 hover:underline">{t("continue")}</Link>
                            : tc("empty")}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
