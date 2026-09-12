import type { Schemas } from "@/lib/api/client";
import { dateShort, dateTimeShort } from "@/lib/format";

type Alert = Schemas["AlertResponse"];
type T = (key: string, values?: Record<string, string | number>) => string;

/**
 * The alert in the reader's language, built from its kind and payload. The API's own `title` and
 * `body` are English and only used for a kind this screen does not know, or a payload that lacks
 * what the sentence needs (alerts written before the payload carried it).
 */
export function alertText(a: Alert, t: T, risk: (code: string) => string, locale: string): { title: string; body: string } {
  const p = (a.payload ?? {}) as Record<string, unknown>;
  const container = a.container_number ?? "";
  const str = (k: string) => (typeof p[k] === "string" ? (p[k] as string) : null);
  const num = (k: string) => (typeof p[k] === "number" ? (p[k] as number) : typeof p[k] === "string" && p[k] !== "" && !Number.isNaN(Number(p[k])) ? Number(p[k]) : null);
  try {
    switch (a.kind) {
      case "DND_RISK": {
        const code = str("risk");
        const lfd = str("last_free_day");
        if (!code || !container) break;
        const title = code === "INCURRING" ? t("text.DND_RISK.titleRunning", { container }) : t("text.DND_RISK.title", { container, risk: risk(code) });
        if (!lfd) return { title, body: t("text.DND_RISK.bodyNoLfd") };
        if (code === "INCURRING") return { title, body: t("text.DND_RISK.bodyRunning", { lfd: dateShort(lfd, locale) }) };
        const days = Math.round((new Date(lfd).getTime() - Date.now()) / 86_400_000);
        return { title, body: days >= 0 ? t("text.DND_RISK.bodyLeft", { lfd: dateShort(lfd, locale), days }) : t("text.DND_RISK.body", { lfd: dateShort(lfd, locale) }) };
      }
      case "ETA_CHANGED": {
        const hours = num("delta_hours");
        const eta = str("eta");
        if (hours === null || !eta || !container) break;
        const previous = str("previous_eta");
        return {
          title: t("text.ETA_CHANGED.title", { container, hours: Math.abs(Math.round(hours)), direction: t(hours > 0 ? "text.ETA_CHANGED.later" : "text.ETA_CHANGED.earlier") }),
          body: previous ? t("text.ETA_CHANGED.body", { eta: dateTimeShort(eta, locale), previous: dateTimeShort(previous, locale) }) : t("text.ETA_CHANGED.bodyNoPrevious", { eta: dateTimeShort(eta, locale) }),
        };
      }
      case "TRACKING_DATA_MISSING": {
        const provider = str("provider");
        const hours = num("hours");
        if (!provider || hours === null || !container) break;
        return { title: t("text.TRACKING_DATA_MISSING.title", { container }), body: t("text.TRACKING_DATA_MISSING.body", { provider, hours }) };
      }
      case "TRACKING_PROVIDER_DOWN": {
        const provider = str("provider");
        if (!provider) break;
        return { title: t("text.TRACKING_PROVIDER_DOWN.title", { provider }), body: t("text.TRACKING_PROVIDER_DOWN.body", { provider }) };
      }
      case "TRACKING_DELIVERY_FAILED": {
        const provider = str("provider");
        const attempts = num("attempts");
        const received = str("received_at");
        if (!provider || attempts === null || !received || !container) break;
        return {
          title: t("text.TRACKING_DELIVERY_FAILED.title", { container }),
          body: t("text.TRACKING_DELIVERY_FAILED.body", { provider, received: dateTimeShort(received, locale), attempts }),
        };
      }
      default:
        break;
    }
  } catch {
    // a message key or a value the formatter refuses: the API's sentence is better than a crash
  }
  return { title: a.title, body: a.body };
}
