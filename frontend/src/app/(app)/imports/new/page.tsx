import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { PageHeader } from "@/components/layout/AppShell";
import Breadcrumb from "@/components/shared/Breadcrumb";
import ImportWizard from "@/features/imports/ImportWizard";
import { api } from "@/lib/api/client";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("importWizard");
  return { title: t("title") };
}

export default async function NewImportPage({ searchParams }: { searchParams: Promise<{ job?: string }> }) {
  const [{ job }, t, ti] = await Promise.all([searchParams, getTranslations("importWizard"), getTranslations("imports")]);
  let initial = null;
  if (job) {
    const { data } = await api.GET("/api/v1/imports/{import_id}", { params: { path: { import_id: job } } });
    if (data && data.status !== "DONE") initial = data;
  }
  return (
    <>
      {/* The title right below already says "Importer des commandes" — the breadcrumb only needs the back link (audit B21). */}
      <Breadcrumb backHref="/imports" backLabel={ti("title")} />
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      {/* The next-step card lives inside the wizard now: it has to follow the live client step (audit B20), which this server page cannot see. */}
      <div id="wizard" className="scroll-mt-6">
        <ImportWizard initialJob={initial} />
      </div>
    </>
  );
}
