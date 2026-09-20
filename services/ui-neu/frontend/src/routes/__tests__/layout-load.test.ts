// Unit tests for the +layout.ts `load` guard itself (not the +layout.svelte
// component — see layout-guest.test.ts for that). Tokenless requests are a
// valid browsing state (guest, backend-side) — the load guard no longer
// attempts any acquisition or redirect based on token presence; it only
// hydrates config and runs the first-run setup check.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { isRedirect } from "@sveltejs/kit";
import type { LayoutLoad } from "../$types";

const getTokenMock = vi.fn<() => string | null>(() => null);
vi.mock("$lib/api/client", () => ({
  getToken: () => getTokenMock(),
}));

const hydrateConfigMock = vi.fn(() => Promise.resolve());
vi.mock("$lib/stores/config", () => ({
  hydrateConfig: () => hydrateConfigMock(),
}));

function loadArgs(pathname: string, fetchImpl: typeof fetch = vi.fn()) {
  return {
    url: new URL(`http://localhost${pathname}`),
    fetch: fetchImpl,
  } as unknown as Parameters<LayoutLoad>[0];
}

describe("+layout.ts load guard", () => {
  beforeEach(() => {
    vi.resetModules();
    getTokenMock.mockReset();
    getTokenMock.mockReturnValue(null);
    hydrateConfigMock.mockClear();
  });

  it("no token + non-auth route: hydrates config and does not redirect", async () => {
    const { load } = await import("../+layout");
    const result = await load(loadArgs("/"));

    expect(hydrateConfigMock).toHaveBeenCalledTimes(1);
    expect(result).toEqual({});
  });

  it("token present: behaves the same as no token (no redirect)", async () => {
    getTokenMock.mockReturnValue("existing-token");

    const { load } = await import("../+layout");
    const result = await load(loadArgs("/"));

    expect(result).toEqual({});
  });

  it("auth route (/login) + no token: no redirect", async () => {
    const { load } = await import("../+layout");
    const result = await load(loadArgs("/login"));

    expect(result).toEqual({});
  });

  it("re-throws a genuine SvelteKit redirect from the setup-status check", async () => {
    vi.doMock("$lib/features", () => ({ features: { setup: true } }));
    const fetchImpl = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ first_run: true }),
      }),
    ) as unknown as typeof fetch;

    const { load } = await import("../+layout");

    let caught: unknown;
    try {
      await load(loadArgs("/", fetchImpl));
    } catch (e) {
      caught = e;
    }
    expect(isRedirect(caught)).toBe(true);
    expect((caught as { location: string }).location).toBe("/setup");

    vi.doUnmock("$lib/features");
  });
});
