import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

/**
 * Optimistic redirects only. In @clerk/nextjs v7 the middleware is not the security boundary:
 * every page, layout, route handler and server action calls `auth.protect()` itself (see lib/auth.ts).
 */
const PUBLIC = [/^\/sign-in(\/.*)?$/, /^\/sign-up(\/.*)?$/, /^\/choose-organization(\/.*)?$/];

export default clerkMiddleware(async (auth, req) => {
  const { pathname } = req.nextUrl;
  if (PUBLIC.some((r) => r.test(pathname))) return;

  const { isAuthenticated, sessionStatus, orgId, redirectToSignIn } = await auth();
  if (!isAuthenticated) {
    if (sessionStatus === "pending") {
      const url = req.nextUrl.clone();
      url.pathname = "/choose-organization";
      return NextResponse.redirect(url);
    }
    return redirectToSignIn({ returnBackUrl: req.url });
  }
  if (!orgId) {
    const url = req.nextUrl.clone();
    url.pathname = "/choose-organization";
    return NextResponse.redirect(url);
  }
});

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
    "/__clerk/(.*)",
  ],
};
