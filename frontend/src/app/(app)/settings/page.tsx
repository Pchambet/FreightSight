import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/AppShell";
import SettingsForm from "@/features/settings/SettingsForm";
import { api } from "@/lib/api/client";

export const metadata: Metadata = { title: "Settings" };

export default async function SettingsPage() {
  const { data, error } = await api.GET("/api/v1/organization");
  if (error || !data) throw new Error("The API returned an error.");
  return (
    <>
      <PageHeader title="Settings" subtitle="Organization defaults used by the allocation engine and the demurrage alerts." />
      <SettingsForm org={data} />
    </>
  );
}
