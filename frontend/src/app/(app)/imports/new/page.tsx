import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { PageHeader } from "@/components/layout/AppShell";
import Breadcrumb from "@/components/shared/Breadcrumb";
import ApiErrorNotice from "@/components/shared/ApiErrorNotice";
import ImportSteps from "@/features/imports/ImportSteps";
import ImportWizard from "@/features/imports/ImportWizard";
import { importStepStates } from "@/features/imports/stepStates";
import { api, problemMessage } from "@/lib/api/client";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("importWizard");
  return { title: t("title") };
}

/** A preview refused for a reason the screen already says in its own words, or shows as its report. */
const SAID_BY_THE_SCREEN = new Set(["MAPPING_INCOMPLETE", "NO_VALID_ROWS"]);

export default async function NewImportPage({ searchParams }: { searchParams: Promise<{ job?: string; kind?: string }> }) {
  const [{ job, kind }, t, ti, kindsRes, org, jobsRes] = await Promise.all([
    searchParams,
    getTranslations("importWizard"),
    getTranslations("imports"),
    api.GET("/api/v1/imports/kinds"),
    api.GET("/api/v1/organization"),
    api.GET("/api/v1/imports"),
  ]);
  const kinds = kindsRes.data ?? [];
  const base = org.data?.base_currency ?? "EUR";
  const states = await importStepStates(jobsRes.data ?? [], base);
  // One file, once it is dropped: its columns, its preview, then what it did. A file taken back has
  // nothing left to show here: the steps are.
  const file = job ? (await api.GET("/api/v1/imports/{import_id}", { params: { path: { import_id: job } } })).data : undefined;
  if (!kinds.length) {
    return (
      <>
        <Breadcrumb backHref="/imports" backLabel={ti("title")} />
        <PageHeader title={t("title")} />
        <ApiErrorNotice error={kindsRes.error} retryHref="/imports/new" />
      </>
    );
  }
  if (!file || file.undone_at) {
    // A remedy link (« importez d'abord le suivi des conteneurs ») opens on that kind's step.
    const current = kinds.find((k) => k.kind === kind)?.kind ?? null;
    return (
      <>
        <Breadcrumb backHref="/imports" backLabel={ti("title")} />
        <PageHeader title={t("title")} subtitle={ti("subtitle")} />
        <ImportSteps kinds={kinds} states={states} current={current} />
      </>
    );
  }
  // The old one-row-per-order format is no numbered step.
  const numbered = kinds.filter((k) => k.kind !== "LEGACY_PO_CONTAINER");
  const n = numbered.findIndex((k) => k.kind === file.kind) + 1;
  const title = t(`kinds.${file.kind}.title`);
  // A preview refused as a whole is about the columns: said there, in the reader's language, for as
  // long as the import holds that refusal — a file dropped a moment ago, or one taken up again.
  const refused = file.status === "PARSED" && file.report.code && !SAID_BY_THE_SCREEN.has(file.report.code) ? await problemMessage(file.report, t("mapping.failed")) : null;
  return (
    <>
      <Breadcrumb backHref="/imports" backLabel={ti("title")} />
      <PageHeader
        title={n ? t("stepList.stepOf", { n, total: numbered.length, title }) : title}
        subtitle={t("fileMeta", { file: file.original_filename ?? t("mapping.fallbackFilename"), rows: file.row_count })}
      />
      {/* Keyed by the file and what it is read as: the next one, dropped from this screen's steps, or
          this one read as another kind, starts from its own state. */}
      <ImportWizard key={`${file.id}:${file.kind}`} kinds={kinds} initialJob={file} initialMappingError={refused} states={states} baseCurrency={base} />
    </>
  );
}
