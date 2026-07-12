import { redirect } from "@sveltejs/kit";
import type { LayoutLoad } from "./$types";
import { hydrateConfig } from "$lib/stores/config";
import { getToken } from "$lib/api/client";
import { guestLogin } from "$lib/api/auth";
import { applyLogin } from "$lib/stores/auth";
import { features } from "$lib/features";

export const prerender = false;
export const ssr = false;

// Once setup is confirmed complete, stop checking on every navigation.
// Only a hard page refresh (F5) resets this, which is the correct behavior
// since completing setup or clearing the DB are deliberate actions.
let setupConfirmedComplete = false;

// Once a guest-acquisition attempt fails (guest access disabled / backend
// down), stop retrying on every navigation for the rest of this page load.
// Only a hard page refresh resets this.
let guestUnavailable = false;

// Hydrate feature flags once per page load.
let configHydrated = false;

export const load: LayoutLoad = async ({ url, fetch }) => {
  if (!configHydrated) {
    await hydrateConfig();
    configHydrated = true;
  }

  const path = url.pathname;
  const isAuthRoute =
    path.startsWith("/login") || path.startsWith("/change-password");

  // Auth guard: unauthenticated visitors first get one passwordless guest-
  // acquisition attempt (spec 2026-07-12-guest-autologin); only when that
  // fails (guest access disabled / backend down) do they go to /login.
  // One attempt per page load: a failure is remembered so subsequent
  // client-side navigations redirect immediately instead of re-hammering
  // the endpoint. NOTE: redirect() throws, so it must stay OUTSIDE the try.
  if (!isAuthRoute && getToken() === null) {
    let acquired = false;
    if (!guestUnavailable) {
      try {
        applyLogin(await guestLogin());
        acquired = true;
      } catch {
        guestUnavailable = true;
      }
    }
    if (!acquired) {
      redirect(307, "/login");
    }
  }

  // Skip setup check if already on /setup
  if (url.pathname.startsWith("/setup")) return {};

  // Setup wizard backend is MISSING in v3 — skip the first-run redirect until a
  // setup-status endpoint lands (feature-flagged off). The block below revives
  // when features.setup flips to true.
  if (!features.setup) return {};

  // Skip if we already know setup is done (cached from a previous navigation)
  if (setupConfirmedComplete) return {};

  try {
    const resp = await fetch("/api/setup/status");
    if (resp.ok) {
      const status = await resp.json();
      if (status.first_run === true) {
        redirect(307, "/setup");
      }
      // Setup is complete - cache this so we don't re-check on every click
      setupConfirmedComplete = true;
    }
    // Non-ok response (503, etc.) - ARM unreachable, don't redirect
  } catch (e) {
    // Re-throw SvelteKit redirects (they use throw internally)
    if (e && typeof e === "object" && "status" in e && "location" in e) throw e;
    // ARM unreachable - don't redirect, let the normal UI handle it
  }

  return {};
};
