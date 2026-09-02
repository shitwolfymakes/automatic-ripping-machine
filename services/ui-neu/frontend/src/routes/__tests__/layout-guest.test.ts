import { describe, it, expect, vi, afterEach } from "vitest";
import { renderComponent, screen, cleanup, fireEvent } from "$lib/test-utils";
import Layout from "../+layout.svelte";
import { createRawSnippet } from "svelte";

// Writable, not readable: +layout.svelte's guest bounce keys off
// $page.url.pathname, so a fixed pathname makes that effect untestable.
vi.mock("$app/stores", async () => {
  const { writable } = await import("svelte/store");
  const _page = writable({ url: { pathname: "/" }, params: {} });
  return {
    page: { subscribe: _page.subscribe },
    // Test-only helper — not part of the real module's public API.
    __setPathname: (pathname: string) => _page.set({ url: { pathname }, params: {} }),
  };
});

async function setPathname(pathname: string) {
  const stores = (await import("$app/stores")) as unknown as {
    __setPathname: (p: string) => void;
  };
  stores.__setPathname(pathname);
}

const gotoMock = vi.fn();
vi.mock("$app/navigation", () => ({
  goto: (...args: unknown[]) => gotoMock(...args),
}));

const getTokenMock = vi.fn(() => null as string | null);
vi.mock("$lib/api/client", () => ({
  setUnauthorizedHandler: vi.fn(),
  getToken: () => getTokenMock(),
}));

const apiLogoutMock = vi.fn(() => Promise.resolve());
vi.mock("$lib/api/auth", () => ({
  logout: () => apiLogoutMock(),
}));

vi.mock("$lib/stores/auth", async () => {
  const { derived, writable } = await import("svelte/store");
  // Mirrors the real store's split: isAdmin reads the persisted role, but
  // isGuest is simply "no token" — NOT role === 'guest'. A guest never logs
  // in, so its role is null; a role-based isGuest would report false for an
  // anonymous visitor and show them admin chrome.
  const _role = writable<string | null>("admin");
  const _isAuthenticated = writable<boolean>(true);
  return {
    initAuth: vi.fn(),
    logoutLocal: vi.fn(),
    role: { subscribe: _role.subscribe },
    isAdmin: derived(_role, (r) => r === "admin"),
    isGuest: derived(_isAuthenticated, (a) => !a),
    // Test-only helper — sets both halves the way a real session would, so a
    // test can't leave the two in a combination production never produces.
    __setSession: (kind: "admin" | "guest") => {
      _role.set(kind === "admin" ? "admin" : null);
      _isAuthenticated.set(kind === "admin");
    },
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
    await setPathname("/");
    gotoMock.mockClear();
    apiLogoutMock.mockClear();
    apiLogoutMock.mockResolvedValue(undefined);
    getTokenMock.mockReset();
    getTokenMock.mockReturnValue(null);
    const auth = (await import("$lib/stores/auth")) as unknown as {
      __setSession: (kind: "admin" | "guest") => void;
    };
    auth.__setSession("admin");
  });

  it("hides the Settings nav link for guests", async () => {
    const auth = (await import("$lib/stores/auth")) as unknown as {
      __setSession: (kind: "admin" | "guest") => void;
    };
    auth.__setSession("guest");
    renderComponent(Layout, { props: { children: childSnippet() } });
    expect(screen.queryByText("Settings")).not.toBeInTheDocument();
  });

  it("hides the quick-actions flyout for guests", async () => {
    const auth = (await import("$lib/stores/auth")) as unknown as {
      __setSession: (kind: "admin" | "guest") => void;
    };
    auth.__setSession("guest");
    renderComponent(Layout, { props: { children: childSnippet() } });
    expect(screen.queryByTitle("Quick actions")).not.toBeInTheDocument();
  });

  it("renders Settings link + flyout for admin", async () => {
    const auth = (await import("$lib/stores/auth")) as unknown as {
      __setSession: (kind: "admin" | "guest") => void;
    };
    auth.__setSession("admin");
    renderComponent(Layout, { props: { children: childSnippet() } });
    expect(screen.getByText("Settings")).toBeInTheDocument();
    expect(screen.getByTitle("Quick actions")).toBeInTheDocument();
  });

  it("guest sees a Login button instead of the sign-out icon", async () => {
    const auth = (await import("$lib/stores/auth")) as unknown as {
      __setSession: (kind: "admin" | "guest") => void;
    };
    auth.__setSession("guest");
    renderComponent(Layout, { props: { children: childSnippet() } });
    expect(screen.getByText("Login")).toBeInTheDocument();
    expect(screen.queryByTitle("Sign out")).not.toBeInTheDocument();
  });

  it("admin keeps the sign-out icon", async () => {
    const auth = (await import("$lib/stores/auth")) as unknown as {
      __setSession: (kind: "admin" | "guest") => void;
    };
    auth.__setSession("admin");
    renderComponent(Layout, { props: { children: childSnippet() } });
    expect(screen.getByTitle("Sign out")).toBeInTheDocument();
    expect(screen.queryByText("Login")).not.toBeInTheDocument();
  });
});

describe("Layout tokenless browsing", () => {
  afterEach(async () => {
    cleanup();
    await setPathname("/");
    gotoMock.mockClear();
    apiLogoutMock.mockClear();
    apiLogoutMock.mockResolvedValue(undefined);
    getTokenMock.mockReset();
    getTokenMock.mockReturnValue(null);
    const auth = (await import("$lib/stores/auth")) as unknown as {
      __setSession: (kind: "admin" | "guest") => void;
    };
    auth.__setSession("admin");
  });

  it("renders as guest (Login button) with no token and no acquisition attempt", async () => {
    getTokenMock.mockReturnValue(null);
    const auth = (await import("$lib/stores/auth")) as unknown as {
      __setSession: (kind: "admin" | "guest") => void;
    };
    auth.__setSession("guest");

    renderComponent(Layout, { props: { children: childSnippet() } });

    expect(screen.getByText("Login")).toBeInTheDocument();
    expect(gotoMock).not.toHaveBeenCalled();
  });

  it("sign-out does a best-effort logout, clears local session, and goes to /", async () => {
    getTokenMock.mockReturnValue("admin-token");

    renderComponent(Layout, { props: { children: childSnippet() } });
    const signOutButton = screen.getByTitle("Sign out");
    await fireEvent.click(signOutButton);

    const { logoutLocal } = (await import("$lib/stores/auth")) as unknown as {
      logoutLocal: ReturnType<typeof vi.fn>;
    };
    expect(apiLogoutMock).toHaveBeenCalledTimes(1);
    expect(logoutLocal).toHaveBeenCalled();
    expect(gotoMock).toHaveBeenCalledWith("/");
  });

  it("sign-out still goes to / even if the server-side logout call fails", async () => {
    getTokenMock.mockReturnValue("admin-token");
    apiLogoutMock.mockRejectedValueOnce(new Error("network error"));

    renderComponent(Layout, { props: { children: childSnippet() } });
    const signOutButton = screen.getByTitle("Sign out");
    await fireEvent.click(signOutButton);

    const { logoutLocal } = (await import("$lib/stores/auth")) as unknown as {
      logoutLocal: ReturnType<typeof vi.fn>;
    };
    expect(logoutLocal).toHaveBeenCalled();
    expect(gotoMock).toHaveBeenCalledWith("/");
  });
});

describe("Layout guest bounce off /settings", () => {
  afterEach(async () => {
    cleanup();
    await setPathname("/");
    gotoMock.mockClear();
    const auth = (await import("$lib/stores/auth")) as unknown as {
      __setSession: (kind: "admin" | "guest") => void;
    };
    auth.__setSession("admin");
  });

  async function renderAt(pathname: string, kind: "admin" | "guest") {
    const auth = (await import("$lib/stores/auth")) as unknown as {
      __setSession: (k: "admin" | "guest") => void;
    };
    auth.__setSession(kind);
    await setPathname(pathname);
    renderComponent(Layout, { props: { children: childSnippet() } });
  }

  it("redirects a guest who lands on /settings to the dashboard", async () => {
    await renderAt("/settings", "guest");
    expect(gotoMock).toHaveBeenCalledWith("/");
  });

  it("redirects a guest who navigates to /settings after mounting", async () => {
    await renderAt("/", "guest");
    expect(gotoMock).not.toHaveBeenCalled();
    await setPathname("/settings");
    expect(gotoMock).toHaveBeenCalledWith("/");
  });

  it("leaves an admin on /settings alone", async () => {
    await renderAt("/settings", "admin");
    expect(gotoMock).not.toHaveBeenCalled();
  });

  it("does not bounce a guest off a non-settings route", async () => {
    await renderAt("/jobs", "guest");
    expect(gotoMock).not.toHaveBeenCalled();
  });
});
