import type { Metadata } from "next";
import { OrganizationList, TaskChooseOrganization } from "@clerk/nextjs";
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

export const metadata: Metadata = { title: "Choose an organization" };

/**
 * Two cases land here: a freshly signed-in user whose session is `pending` (Clerk's
 * choose-organization task), and an active user with no active organization.
 */
export default async function ChooseOrganizationPage() {
  const a = await auth();
  if (a.isAuthenticated && a.orgId) redirect("/");
  if (!a.isAuthenticated && a.sessionStatus !== "pending") redirect("/sign-in");

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <div className="space-y-4">
        <div className="text-center">
          <h1 className="text-lg font-semibold">Choose your organization</h1>
          <p className="text-sm text-slate-500">Every purchase order, container and cost belongs to one organization.</p>
        </div>
        {a.sessionStatus === "pending" ? (
          <TaskChooseOrganization redirectUrlComplete="/" />
        ) : (
          <OrganizationList hidePersonal afterSelectOrganizationUrl="/" afterCreateOrganizationUrl="/" />
        )}
      </div>
    </div>
  );
}
