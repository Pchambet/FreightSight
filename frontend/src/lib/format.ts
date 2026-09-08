import { DEFAULT_LOCALE, type Locale } from "@/i18n/config";

/** BCP 47 tag behind an app locale: French uses the French conventions (12 500,50 €, 08/09/2026). */
function intl(locale: string): string {
  return locale === "fr" ? "fr-FR" : "en-GB";
}

/** Money arrives from the API as decimal strings ("1234.56"). Formatting only, never arithmetic on floats. */
export function money(amount: string | number | null | undefined, currency: string, locale: string = DEFAULT_LOCALE): string {
  if (amount === null || amount === undefined) return "—";
  const value = typeof amount === "number" ? amount : Number(amount);
  if (!Number.isFinite(value)) return "—";
  return new Intl.NumberFormat(intl(locale), {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function unitCost(amount: string | number, currency: string, locale: string = DEFAULT_LOCALE): string {
  const value = typeof amount === "number" ? amount : Number(amount);
  if (!Number.isFinite(value)) return "—";
  return new Intl.NumberFormat(intl(locale), {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(value);
}

export function qty(value: string | number, locale: string = DEFAULT_LOCALE): string {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat(intl(locale), { maximumFractionDigits: 4 }).format(n);
}

export function pct(value: string | number, locale: string = DEFAULT_LOCALE): string {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${new Intl.NumberFormat(intl(locale), { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)} %`;
}

/** Numeric in French (08/09/2026), abbreviated month in English (08 Sep 2026). */
export function dateShort(value: string | null | undefined, locale: string = DEFAULT_LOCALE): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  const style: Intl.DateTimeFormatOptions =
    locale === ("fr" satisfies Locale)
      ? { day: "2-digit", month: "2-digit", year: "numeric" }
      : { day: "2-digit", month: "short", year: "numeric" };
  return new Intl.DateTimeFormat(intl(locale), style).format(d);
}

export function daysUntil(isoDate: string | null | undefined): number | null {
  if (!isoDate) return null;
  const target = new Date(`${isoDate}T00:00:00Z`).getTime();
  const today = new Date();
  const todayUtc = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
  return Math.round((target - todayUtc) / 86_400_000);
}
