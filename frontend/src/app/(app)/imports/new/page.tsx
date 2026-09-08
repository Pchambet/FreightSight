import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/AppShell";
import ImportWizard from "@/features/imports/ImportWizard";
import { api } from "@/lib/api/client";

export const metadata: Metadata = { title: "New import" };

export default async function NewImportPage({ searchParams }: { searchParams: Promise<{ job?: string }> }) {
  const { job } = await searchParams;
  let initial = null;
  if (job) {
    const { data } = await api.GET("/api/v1/imports/{import_id}", { params: { path: { import_id: job } } });
    if (data && data.status !== "DONE") initial = data;
  }
  return (
    <>
      <PageHeader title="Import purchase orders" subtitle="Upload, map the columns, review the validation report, then commit. Nothing is written before the last step." />
      <ImportWizard initialJob={initial} />
    </>
  );
}
