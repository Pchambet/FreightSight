import { AppShell } from "@/components/layout/AppShell";
import { api } from "@/lib/api/client";
import { requireAuth } from "@/lib/auth";

async function orgName(): Promise<string | undefined> {
  try {
    const { data } = await api.GET("/api/v1/organization");
    return data?.name;
  } catch {
    return undefined;
  }
}

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  await requireAuth();
  const name = await orgName();
  return <AppShell orgName={name}>{children}</AppShell>;
}
