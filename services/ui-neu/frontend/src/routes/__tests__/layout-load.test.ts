// Unit tests for the +layout.ts `load` guard itself (not the +layout.svelte
// component — see layout-guest.test.ts for that). This guard runs BEFORE any
// component code, so it needs its own passwordless guest-acquisition attempt;
// see spec 2026-07-12-guest-autologin and the live-trace defect it fixes
// (nav to /login at t=88ms, preceding the component's guest POST at t=106ms).
import { describe, it, expect, vi, beforeEach } from "vitest";
import { isRedirect } from "@sveltejs/kit";
import type { LayoutLoad } from "../$types";

const getTokenMock = vi.fn<() => string | null>(() => null);
vi.mock("$lib/api/client", () => ({
  getToken: () => getTokenMock(),
}));

const guestLoginMock = vi.fn();
vi.mock("$lib/api/auth", () => ({
  guestLogin: () => guestLoginMock(),
}));

const applyLoginMock = vi.fn();
vi.mock("$lib/stores/auth", () => ({
  applyLogin: (...args: unknown[]) => applyLoginMock(...args),
}));

const hydrateConfigMock = vi.fn(() => Promise.resolve());
vi.mock("$lib/stores/config", () => ({
  hydrateConfig: () => hydrateConfigMock(),
}));

function loadArgs(pathname: string) {
  return {
    url: new URL(`http://localhost${pathname}`),
    fetch: vi.fn(),
  } as unknown as Parameters<LayoutLoad>[0];
}

describe("+layout.ts load guard — guest auto-acquire", () => {
  beforeEach(() => {
    vi.resetModules();
    getTokenMock.mockReset();
    getTokenMock.mockReturnValue(null);
    guestLoginMock.mockReset();
    applyLoginMock.mockClear();
    hydrateConfigMock.mockClear();
  });

  it("no token + guest acquisition succeeds: applyLogin is called and no redirect is thrown", async () => {
    guestLoginMock.mockResolvedValue({
      access_token: "guest-token",
      expires_at: "2099-01-01T00:00:00Z",
      password_must_change: false,
      role: "guest",
    });

    const { load } = await import("../+layout");
    const result = await load(loadArgs("/"));

    expect(guestLoginMock).toHaveBeenCalledTimes(1);
    expect(applyLoginMock).toHaveBeenCalledWith({
      access_token: "guest-token",
      expires_at: "2099-01-01T00:00:00Z",
      password_must_change: false,
      role: "guest",
    });
    expect(result).toEqual({});
  });

  it("no token + guestLogin rejects: redirects to /login, and a second call does not re-hit guestLogin but still redirects", async () => {
    guestLoginMock.mockRejectedValue(new Error("403 guest disabled"));

    const { load } = await import("../+layout");

    let firstError: unknown;
    try {
      await load(loadArgs("/"));
    } catch (e) {
      firstError = e;
    }
    expect(isRedirect(firstError)).toBe(true);
    expect((firstError as { location: string }).location).toBe("/login");
    expect(guestLoginMock).toHaveBeenCalledTimes(1);

    // Second load call: guestUnavailable memory means no second guestLogin
    // call, but it must still redirect.
    let secondError: unknown;
    try {
      await load(loadArgs("/"));
    } catch (e) {
      secondError = e;
    }
    expect(isRedirect(secondError)).toBe(true);
    expect((secondError as { location: string }).location).toBe("/login");
    expect(guestLoginMock).toHaveBeenCalledTimes(1);
  });

  it("token present: guestLogin is never called", async () => {
    getTokenMock.mockReturnValue("existing-token");

    const { load } = await import("../+layout");
    const result = await load(loadArgs("/"));

    expect(guestLoginMock).not.toHaveBeenCalled();
    expect(applyLoginMock).not.toHaveBeenCalled();
    expect(result).toEqual({});
  });

  it("auth route (/login) + no token: no acquisition attempt, no redirect", async () => {
    const { load } = await import("../+layout");
    const result = await load(loadArgs("/login"));

    expect(guestLoginMock).not.toHaveBeenCalled();
    expect(applyLoginMock).not.toHaveBeenCalled();
    expect(result).toEqual({});
  });
});
