import { AppShell } from "@/components/layout/AppShell";
import OrgGuard from "@/components/layout/OrgGuard";
import { api } from "@/lib/api/client";
import { requireAuth } from "@/lib/auth";

async function org(): Promise<{ name?: string; unreadAlerts: number }> {
  try {
    const { data } = await api.GET("/api/v1/organization");
    return { name: data?.name, unreadAlerts: data?.unread_alerts ?? 0 };
  } catch {
    return { unreadAlerts: 0 };
  }
}

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const { orgId } = await requireAuth();
  const { name, unreadAlerts } = await org();
  return (
    <AppShell orgName={name} unreadAlerts={unreadAlerts}>
      {orgId ? <OrgGuard renderedFor={orgId} /> : null}
      {children}
    </AppShell>
  );
}
