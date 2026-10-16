import Link from "next/link";
import { useTranslations } from "next-intl";
import { Info } from "lucide-react";

/** What the API says about the containers a landed figure leaves out: how many in all
 * (`containers_without_charge`), how many of those have charges on file that cannot be placed yet
 * (`containers_held`), and the orders with no exchange rate that hold them (`held_orders`). */
export type LeftOut = { containers_without_charge?: number | null; containers_held?: number | null; held_orders?: string[] | null };

/** The orders as one ICU pair: `orderCount` picks the sentence, `orders` names them. */
export const heldParams = (orders: string[] | null | undefined) => ({ orderCount: orders?.length ?? 0, orders: (orders ?? []).join(", ") });

/**
 * Why a landed figure counts fewer containers than the FOB beside it. Two different reasons, never
 * one sentence for both: a container with no charge at all, estimated or invoiced, and one whose
 * charges are on file but cannot be placed yet (most often an order with no exchange rate). Telling
 * the second as the first reads as "the forwarder's invoice was never entered", and invites a person
 * to enter it twice. The API leaves both out of every landed figure rather than pass their FOB off as
 * a landed cost; this says so next to the figures.
 */
export default function WithoutCharge({ of, href = "/containers", className = "" }: { of: LeftOut | null | undefined; href?: string | null; className?: string }) {
  const t = useTranslations("withoutCharge");
  const all = of?.containers_without_charge ?? 0;
  const held = Math.min(of?.containers_held ?? 0, all);
  const bare = all - held;
  if (!all) return null;
  const sentences = [bare > 0 ? t("total", { count: bare }) : null, held > 0 ? t("held", { count: held, ...heldParams(of?.held_orders) }) : null].filter(Boolean).join(" ");
  return (
    <p role="note" className={`flex items-start gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 ${className}`}>
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" aria-hidden />
      <span>
        {sentences}
        {href ? (
          <>
            {" "}
            <Link href={href} className="font-medium underline underline-offset-2 hover:no-underline print:no-underline">{t("see")}</Link>
          </>
        ) : null}
      </span>
    </p>
  );
}

/** The containers left out, in a few words: those with no charge, those with charges held. */
export function leftOutText(t: (key: "count" | "heldCount", values: { count: number }) => string, of: LeftOut | null | undefined): string | null {
  const all = of?.containers_without_charge ?? 0;
  const held = Math.min(of?.containers_held ?? 0, all);
  if (!all) return null;
  return [all > held ? t("count", { count: all - held }) : null, held > 0 ? t("heldCount", { count: held }) : null].filter(Boolean).join(" · ");
}

/** The same under a row: how many of its containers were left out and why (`of`), or, for one
 * container or one of its lines (`box`), whether it has no charge at all or charges held. */
export function WithoutChargeLine({ of, box }: { of?: LeftOut | null; box?: { without_charge?: boolean | null; charges_held?: boolean | null; held_orders?: string[] | null } }) {
  const t = useTranslations("withoutCharge");
  if (box) {
    if (!box.without_charge) return null;
    return <span className="block text-xs font-normal text-slate-500">{box.charges_held ? t("heldBox", heldParams(box.held_orders)) : t("box")}</span>;
  }
  const text = leftOutText(t, of);
  return text ? <span className="block text-xs font-normal text-slate-500">{text}</span> : null;
}
