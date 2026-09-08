import "server-only";
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

/**
 * The security boundary for pages and layouts: signed-out users go to sign-in, users without an
 * active organization go to the picker. Returns the Clerk auth object for the request.
 */
export async function requireAuth() {
  const a = await auth();
  if (!a.isAuthenticated) {
    if (a.sessionStatus === "pending") redirect("/choose-organization");
    redirect("/sign-in");
  }
  if (!a.orgId) redirect("/choose-organization");
  return a;
}

/** For Server Actions and Route Handlers: 401/404 instead of a redirect. */
export async function protectAction(): Promise<void> {
  await auth.protect();
}
