import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { PageHeader } from "@/components/layout/AppShell";
import SettingsForm from "@/features/settings/SettingsForm";
import { api } from "@/lib/api/client";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("settings");
  return { title: t("title") };
}

export default async function SettingsPage() {
  const [{ data, error }, t] = await Promise.all([api.GET("/api/v1/organization"), getTranslations("settings")]);
  if (error || !data) throw new Error("api_error"); // thrown, never rendered
  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      <SettingsForm org={data} />
    </>
  );
}
