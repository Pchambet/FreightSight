import type { Metadata } from "next";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { Card, PageHeader, btnSecondary, td, tdRight, th, thRight } from "@/components/layout/AppShell";
import { Money } from "@/components/shared/Money";
import { api } from "@/lib/api/client";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("purchaseOrders");
  return { title: t("title") };
}

export default async function PurchaseOrdersPage() {
  const [p, o, t, tc] = await Promise.all([
    api.GET("/api/v1/purchase-orders"),
    api.GET("/api/v1/organization"),
    getTranslations("purchaseOrders"),
    getTranslations("common"),
  ]);
  const pos = p.data ?? [];
  const cur = o.data?.base_currency ?? "EUR";
  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle", { count: pos.length })} actions={<Link href="/imports/new" className={btnSecondary}>{t("importCta")}</Link>} />
      <Card>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className={th}>{t("th.po")}</th>
                <th className={th}>{t("th.supplier")}</th>
                <th className={th}>{t("th.currency")}</th>
                <th className={thRight}>{t("th.lines")}</th>
                <th className={thRight}>{t("th.fob", { currency: cur })}</th>
                <th className={th}>{t("th.containers")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {pos.length === 0 ? (
                <tr><td colSpan={6} className="px-5 py-14 text-center text-sm text-slate-500">{t("empty")} <Link href="/imports/new" className="text-blue-600 hover:underline">{t("emptyLink")}</Link> {t("emptySuffix")}</td></tr>
              ) : (
                pos.map((po) => (
                  <tr key={po.id} className="hover:bg-slate-50">
                    <td className={td}><Link href={`/purchase-orders/${po.id}`} className="font-medium text-blue-600 hover:underline">{po.po_number}</Link></td>
                    <td className={`${td} text-slate-600`}>{po.supplier_name ?? tc("empty")}</td>
                    <td className={`${td} font-mono text-xs`}>{po.currency}</td>
                    <td className={tdRight}>{po.line_count}</td>
                    <td className={tdRight}><Money amount={po.fob_base} currency={cur} /></td>
                    <td className={`${td} font-mono text-xs text-slate-600`}>{po.container_numbers.join(", ") || <span className="text-slate-400">{t("notLoaded")}</span>}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
