import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { PageHeader } from "@/components/layout/AppShell";
import ImportWizard from "@/features/imports/ImportWizard";
import { api } from "@/lib/api/client";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("importWizard");
  return { title: t("title") };
}

export default async function NewImportPage({ searchParams }: { searchParams: Promise<{ job?: string }> }) {
  const [{ job }, t] = await Promise.all([searchParams, getTranslations("importWizard")]);
  let initial = null;
  if (job) {
    const { data } = await api.GET("/api/v1/imports/{import_id}", { params: { path: { import_id: job } } });
    if (data && data.status !== "DONE") initial = data;
  }
  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      <ImportWizard initialJob={initial} />
    </>
  );
}
