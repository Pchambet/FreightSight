"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { td, th } from "@/components/layout/AppShell";
import ScrollRegion from "@/components/shared/ScrollRegion";
import type { Schemas } from "@/lib/api/client";
import { dateShort, rate as formatRate } from "@/lib/format";

type Issue = Schemas["ImportRowIssue"];

/**
 * What fixes a whole cause, rather than a row: the file to import first, or what to change in this
 * one. Only codes with a remedy that holds for every row of the group are here; the others say their
 * own sentence and nothing more.
 */
const REMEDY: Record<string, { key: string; href?: string }> = {
  UNKNOWN_CONTAINER: { key: "importContainers", href: "/imports/new?kind=CONTAINERS" },
  UNKNOWN_SHIPMENT: { key: "importContainers", href: "/imports/new?kind=CONTAINERS" },
  UNKNOWN_ORDER: { key: "importOrders", href: "/imports/new?kind=PURCHASE_ORDERS" },
  COST_TYPE_UNKNOWN: { key: "typeLabels" },
  COST_TYPE_AMBIGUOUS: { key: "splitLine" },
  ARRIVAL_UNKNOWN: { key: "arrival" },
  PO_UNKNOWN: { key: "ordersThenAgain", href: "/imports/new?kind=PURCHASE_ORDERS" },
  DUPLICATE_COST: { key: "alreadyInBooks" },
  INVOICE_ALREADY_RECORDED: { key: "alreadyInBooks" },
  INVOICE_IN_INBOX: { key: "inInbox", href: "/invoices?filter=review" },
};

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

/** As many different sentences as a group says in full: a file's date columns, one warning each. */
const FEW = 6;

/**
 * Params as the rest of the screen shows them, not raw: a date as a date, a rate as a rate, a field by
 * the header of the mapping step — `field` is the column the row is refused on, and the two columns of
 * DATES_OUT_OF_ORDER are field names too. A file contradicting itself is so about one container or
 * about one B/L: `on` tells the sentence which.
 */
function displayParams(i: Issue, locale: string, fieldName: (field: string) => string): Record<string, string> {
  const params = { ...((i.params ?? {}) as Record<string, string>) };
  const asDay = (v: string) => (ISO_DAY.test(v) ? dateShort(v, locale) : v);
  if (i.field) params.field = fieldName(i.field);
  switch (i.code) {
    case "FX_RATE_DEFAULTED":
    case "FX_RATE_APPLIED":
      return { ...params, rate_date: dateShort(params.rate_date, locale), rate: formatRate(params.rate, locale) };
    case "DATES_OUT_OF_ORDER":
      return { ...params, first: fieldName(params.first), second: fieldName(params.second) };
    case "CONFLICT_IN_FILE":
      return params.shipment_reference
        ? { ...params, on: "bill", values: (params.values ?? "").split(", ").map(asDay).join(", ") }
        : { ...params, on: "container", first: asDay(params.first ?? ""), second: asDay(params.second ?? "") };
    default:
      return params;
  }
}

/**
 * The preview's errors or warnings, one block per cause: its sentence (or, when rows differ, each
 * sentence, or one as an example), which rows, and what fixes them all — « 14 lignes visent des
 * conteneurs inconnus : importez d'abord le suivi des conteneurs ». Every row stays one click away.
 * Field names and codes are internal: the field is named with the mapping step's headers, the code
 * only through its translated sentence.
 */
export default function IssueGroups({ issues, tone, title, fieldName }: { issues: Issue[]; tone: "amber" | "red"; title: string; fieldName: (field: string) => string }) {
  const t = useTranslations("importWizard.issues");
  const tr = useTranslations("importWizard.review");
  const th_ = useTranslations("importWizard.review.th");
  const errorCode = useTranslations("errors");
  const locale = useLocale();
  const sentence = (i: Issue) => (errorCode.has(i.code) ? errorCode(i.code, displayParams(i, locale, fieldName)) : tr("unknownIssue"));
  const byCode = new Map<string, Issue[]>();
  for (const i of issues) byCode.set(i.code, [...(byCode.get(i.code) ?? []), i]);
  const groups = [...byCode].sort((a, b) => b[1].length - a[1].length);
  const color = tone === "amber" ? "text-amber-800" : "text-red-700";
  const border = tone === "amber" ? "border-amber-200 bg-amber-50/40" : "border-red-200 bg-red-50/40";
  return (
    <div>
      <div className={`text-sm font-medium mb-2 ${color}`}>{title}</div>
      <ul className="space-y-2">
        {groups.map(([code, rows]) => {
          const remedy = REMEDY[code];
          // Rows, not issues: a file-wide warning sits on the header row once per column.
          const lines = [...new Set(rows.map((i) => i.row))];
          const shown = lines.slice(0, 8);
          // One sentence for the group when every row says the same; otherwise the few there are, or
          // the first one as an example — never one row's detail presented as every row's.
          const sentences = [...new Set(rows.map(sentence))];
          return (
            <li key={code} className={`rounded-md border px-3 py-2 text-sm ${border}`}>
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                {sentences.length === 1 ? (
                  <span className="text-slate-800">{sentences[0]}</span>
                ) : sentences.length <= FEW ? (
                  <ul className="text-slate-800 space-y-0.5">{sentences.map((s) => <li key={s}>{s}</li>)}</ul>
                ) : (
                  <span className="text-slate-800">{t("example", { row: rows[0].row, sentence: sentences[0] })}</span>
                )}
                <span className="text-xs text-slate-600 tabular-nums">
                  {t("rows", { count: lines.length, list: shown.join(", "), more: lines.length - shown.length })}
                </span>
              </div>
              {remedy ? (
                <p className="mt-1 text-xs text-slate-700">
                  {t(`remedy.${remedy.key}`)}
                  {remedy.href ? (
                    <>
                      {" "}
                      <Link href={remedy.href} className="text-blue-700 underline underline-offset-2 hover:no-underline">{t(`remedyLink.${remedy.key}`)}</Link>
                    </>
                  ) : null}
                </p>
              ) : null}
              {lines.length > 1 || sentences.length > FEW ? (
                <details className="mt-1">
                  <summary className="cursor-pointer text-xs text-slate-600">{t("seeAll", { count: rows.length })}</summary>
                  <ScrollRegion label={sentences.length === 1 ? sentences[0] : t("seeAll", { count: rows.length })} className="mt-2 border border-slate-200 rounded-md max-h-64 overflow-y-auto bg-white">
                    <table className="min-w-full divide-y divide-slate-200 text-xs">
                      <thead className="bg-slate-50"><tr><th className={th}>{th_("row")}</th><th className={th}>{th_("field")}</th><th className={th}>{th_("message")}</th></tr></thead>
                      <tbody className="divide-y divide-slate-100">
                        {rows.slice(0, 200).map((i, idx) => (
                          <tr key={idx}>
                            <td className={td}>{i.row}</td>
                            <td className={td}>{i.field ? fieldName(i.field) : "—"}</td>
                            <td className="px-4 py-2">{sentence(i)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </ScrollRegion>
                </details>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
