import type { ImportJobResponse, Schemas } from "@/lib/api/client";

type KindInfo = Schemas["ImportKindInfo"];

/** The file's columns that no field reads, in the file's order. */
export function unreadColumns(columns: string[], mapping: Record<string, string>): string[] {
  const read = new Set(Object.values(mapping));
  return columns.filter((c) => !read.has(c));
}

/**
 * Nothing is left for a person to decide about the columns: every required field has one, every group
 * of which one is needed has one, and no column of the file goes unread. Such a file goes straight to
 * its preview; any other stops at the columns, where the question is.
 */
export function readsItself(info: KindInfo, job: Pick<ImportJobResponse, "columns" | "mapping">): boolean {
  const mapped = (field: string) => Boolean(job.mapping[field]);
  return (
    info.fields.every((f) => !f.required || mapped(f.field)) &&
    (info.required_one_of ?? []).every((group) => group.some(mapped)) &&
    unreadColumns(job.columns, job.mapping).length === 0
  );
}
