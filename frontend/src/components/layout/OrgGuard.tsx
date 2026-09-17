"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect } from "react";

const KEY = "fs.orgGuard";
/** Long enough for Clerk's own switch (token, cookie, router refresh) to finish by itself. */
const SETTLE_MS = 2000;

/**
 * The active organisation belongs to the Clerk session, not to the tab: switching company in one
 * tab can switch it under another. A page already on screen would then show one company while its
 * buttons act as another — the API refuses (the ids are not that company's), but "Introuvable" on a
 * record you are looking at is no way to find out. So a tab whose screen and session still disagree
 * after a moment goes back to the board, rendered for the company now active.
 *
 * `renderedFor` is the organisation the server rendered this layout for. The wait matters: during
 * an ordinary switch the two disagree for a few hundred milliseconds, and reloading in the middle
 * of it would race the cookie Clerk is about to write. One reload per change at most: if the server
 * still answers for the old organisation, reloading again would loop.
 */
export default function OrgGuard({ renderedFor }: { renderedFor: string }) {
  const { isLoaded, orgId, getToken } = useAuth();

  // The session cookie is one for all tabs, and the last tab to refresh its token wrote it: seen on
  // 17 Sept 2026 with two tabs on two companies, the server answered tab B for the company of tab A.
  // Coming back to this tab, ask Clerk for a fresh token of this tab's company, which is what makes
  // it write the cookie again, before the first click leaves in another company's name.
  useEffect(() => {
    if (!isLoaded) return;
    const claim = () => {
      if (document.visibilityState === "visible") void getToken({ skipCache: true }).catch(() => null);
    };
    window.addEventListener("focus", claim);
    document.addEventListener("visibilitychange", claim);
    return () => {
      window.removeEventListener("focus", claim);
      document.removeEventListener("visibilitychange", claim);
    };
  }, [isLoaded, getToken]);

  useEffect(() => {
    if (!isLoaded || !orgId) return;
    if (orgId === renderedFor) {
      try {
        window.sessionStorage.removeItem(KEY);
      } catch {
        // nothing to forget
      }
      return;
    }
    const timer = window.setTimeout(() => {
      const change = `${renderedFor}>${orgId}`;
      try {
        if (window.sessionStorage.getItem(KEY) === change) return;
        window.sessionStorage.setItem(KEY, change);
      } catch {
        return; // no storage to remember the reload by: a stale page is better than a reload loop
      }
      // A full load on purpose: the layout and the router cache both belong to the other company.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign("/containers");
    }, SETTLE_MS);
    return () => window.clearTimeout(timer);
  }, [isLoaded, orgId, renderedFor]);
  return null;
}
