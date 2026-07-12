import { describe, it, expect, vi, afterEach } from "vitest";
import { renderComponent, screen, cleanup, waitFor, fireEvent } from "$lib/test-utils";
import Layout from "../+layout.svelte";
import { createRawSnippet } from "svelte";

vi.mock("$app/stores", async () => {
  const { readable } = await import("svelte/store");
  return { page: readable({ url: { pathname: "/" }, params: {} }) };
});

const gotoMock = vi.fn();
vi.mock("$app/navigation", () => ({
  goto: (...args: unknown[]) => gotoMock(...args),
}));

let unauthorizedHandler: () => void = () => {};
const getTokenMock = vi.fn(() => null as string | null);
vi.mock("$lib/api/client", () => ({
  setUnauthorizedHandler: vi.fn((fn: () => void) => {
    unauthorizedHandler = fn;
  }),
  getToken: () => getTokenMock(),
}));

const guestLoginMock = vi.fn();
const apiLogoutMock = vi.fn(() => Promise.resolve());
vi.mock("$lib/api/auth", () => ({
  guestLogin: () => guestLoginMock(),
  logout: () => apiLogoutMock(),
}));

vi.mock("$lib/stores/auth", async () => {
  const { derived, writable } = await import("svelte/store");
  const _role = writable<string | null>("admin");
  return {
    initAuth: vi.fn(),
    logoutLocal: vi.fn(),
    applyLogin: vi.fn(() => _role.set("guest")),
    role: { subscribe: _role.subscribe },
    isAdmin: derived(_role, (r) => r === "admin"),
    isGuest: derived(_role, (r) => r === "guest"),
    // Test-only helper — not part of the real module's public API.
    __setRole: (r: string | null) => _role.set(r),
  };
});

vi.mock("$lib/stores/theme", async () => {
  const { writable } = await import("svelte/store");
  return { theme: writable("dark"), toggleTheme: vi.fn() };
});

vi.mock("$lib/stores/colorScheme", async () => {
  const { writable } = await import("svelte/store");
  return {
    colorScheme: writable("default"),
    schemeLocksMode: writable(false),
    loadThemesFromApi: vi.fn(),
  };
});

vi.mock("$lib/stores/dashboard", async () => {
  const { writable } = await import("svelte/store");
  const store = writable({
    db_available: true,
    arm_online: true,
    active_jobs: [],
    drives_online: 1,
    drive_names: {},
    notification_count: 0,
    ripping_enabled: true,
    transcoder_online: false,
    transcoder_stats: null,
    active_transcodes: [],
  });
  return {
    dashboard: {
      ...store,
      start: vi.fn(),
      stop: vi.fn(),
      error: writable(null),
    },
  };
});

vi.mock("$lib/api/dashboard", () => ({
  setRippingEnabled: vi.fn(() => Promise.resolve()),
}));

function childSnippet() {
  return createRawSnippet(() => ({
    render: () => "<p>Page Content</p>",
  }));
}

describe("Layout guest gating", () => {
  afterEach(async () => {
    cleanup();
    gotoMock.mockClear();
    guestLoginMock.mockReset();
    apiLogoutMock.mockClear();
    apiLogoutMock.mockResolvedValue(undefined);
    getTokenMock.mockReset();
    getTokenMock.mockReturnValue(null);
    const auth = (await import("$lib/stores/auth")) as unknown as {
      __setRole: (r: string | null) => void;
    };
    auth.__setRole("admin");
  });

  it("hides the Settings nav link for guests", async () => {
    const auth = (await import("$lib/stores/auth")) as unknown as {
      __setRole: (r: string | null) => void;
    };
    auth.__setRole("guest");
    renderComponent(Layout, { props: { children: childSnippet() } });
    expect(screen.queryByText("Settings")).not.toBeInTheDocument();
  });

  it("hides the quick-actions flyout for guests", async () => {
    const auth = (await import("$lib/stores/auth")) as unknown as {
      __setRole: (r: string | null) => void;
    };
    auth.__setRole("guest");
    renderComponent(Layout, { props: { children: childSnippet() } });
    expect(screen.queryByTitle("Quick actions")).not.toBeInTheDocument();
  });

  it("shows a GUEST badge for guests", async () => {
    const auth = (await import("$lib/stores/auth")) as unknown as {
      __setRole: (r: string | null) => void;
    };
    auth.__setRole("guest");
    renderComponent(Layout, { props: { children: childSnippet() } });
    expect(screen.getByText("GUEST")).toBeInTheDocument();
  });

  it("renders Settings link + flyout for admin", async () => {
    const auth = (await import("$lib/stores/auth")) as unknown as {
      __setRole: (r: string | null) => void;
    };
    auth.__setRole("admin");
    renderComponent(Layout, { props: { children: childSnippet() } });
    expect(screen.getByText("Settings")).toBeInTheDocument();
    expect(screen.getByTitle("Quick actions")).toBeInTheDocument();
    expect(screen.queryByText("GUEST")).not.toBeInTheDocument();
  });
});

describe("Layout guest auto-acquire", () => {
  afterEach(async () => {
    cleanup();
    gotoMock.mockClear();
    guestLoginMock.mockReset();
    apiLogoutMock.mockClear();
    apiLogoutMock.mockResolvedValue(undefined);
    getTokenMock.mockReset();
    getTokenMock.mockReturnValue(null);
    const auth = (await import("$lib/stores/auth")) as unknown as {
      __setRole: (r: string | null) => void;
    };
    auth.__setRole("admin");
  });

  it("auto-acquires a guest session when unauthenticated", async () => {
    getTokenMock.mockReturnValue(null);
    guestLoginMock.mockResolvedValue({
      access_token: "guest-token",
      expires_at: "2099-01-01T00:00:00Z",
      password_must_change: false,
      role: "guest",
    });

    renderComponent(Layout, { props: { children: childSnippet() } });

    await waitFor(() => expect(guestLoginMock).toHaveBeenCalledTimes(1));
    expect(gotoMock).not.toHaveBeenCalledWith("/login");
  });

  it("falls back to /login when guest acquisition fails", async () => {
    getTokenMock.mockReturnValue(null);
    guestLoginMock.mockRejectedValue(new Error("403 guest disabled"));

    renderComponent(Layout, { props: { children: childSnippet() } });

    await waitFor(() => expect(gotoMock).toHaveBeenCalledWith("/login"));
    expect(guestLoginMock).toHaveBeenCalledTimes(1);
  });

  it("admin logout drops into a guest session when enabled", async () => {
    getTokenMock.mockReturnValue("admin-token");
    guestLoginMock.mockResolvedValue({
      access_token: "guest-token",
      expires_at: "2099-01-01T00:00:00Z",
      password_must_change: false,
      role: "guest",
    });

    renderComponent(Layout, { props: { children: childSnippet() } });
    const signOutButton = screen.getByTitle("Sign out");
    await fireEvent.click(signOutButton);

    await waitFor(() => expect(gotoMock).toHaveBeenCalledWith("/"));
    expect(apiLogoutMock).toHaveBeenCalledTimes(1);
    expect(guestLoginMock).toHaveBeenCalledTimes(1);
  });

  it("admin logout falls back to /login when guest disabled", async () => {
    getTokenMock.mockReturnValue("admin-token");
    guestLoginMock.mockRejectedValue(new Error("403 guest disabled"));

    renderComponent(Layout, { props: { children: childSnippet() } });
    const signOutButton = screen.getByTitle("Sign out");
    await fireEvent.click(signOutButton);

    await waitFor(() => expect(gotoMock).toHaveBeenCalledWith("/login"));
    expect(apiLogoutMock).toHaveBeenCalledTimes(1);
  });
});
