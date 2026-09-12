/** Translate machine-readable invoice line notes (`@code|arg|…`) from the API. */

type NoteTranslator = (key: string, values?: Record<string, string | number>) => string;
type CostTypeTranslator = (key: string) => string;

export function formatInvoiceNote(
  note: string,
  t: NoteTranslator,
  costType: CostTypeTranslator,
): string {
  if (!note.startsWith("@")) return note;
  const [code, ...parts] = note.slice(1).split("|");
  switch (code) {
    case "single_container":
      return t("singleContainer", { container: parts[0] ?? "" });
    case "duplicate_cost":
      return t("duplicateCost", {
        type: costType(parts[0] ?? ""),
        vendor: parts[1] || "—",
        invoice: parts[2] || "—",
        amount: parts[3] ?? "",
        currency: parts[4] ?? "",
      });
    case "unknown_container":
      return t("unknownContainer", { container: parts[0] ?? "" });
    case "no_fx_rate":
      return t("noFxRate", { currency: parts[0] ?? "", date: parts[1] || "—" });
    case "arithmetic_mismatch":
      return t(parts[1] === "more_than" ? "arithmeticMore" : "arithmeticLess", { amount: parts[0] ?? "" });
    case "multi_container":
      return t("multiContainer");
    default:
      return note;
  }
}

export function isDuplicateCostNote(note: string): boolean {
  return note.startsWith("@duplicate_cost|");
}

export function splitInvoiceNotes(notes: string | null | undefined): string[] {
  if (!notes) return [];
  return notes.split("; ").map((n) => n.trim()).filter(Boolean);
}
