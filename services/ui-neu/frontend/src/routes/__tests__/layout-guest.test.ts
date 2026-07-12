import { describe, it, expect, vi, afterEach } from "vitest";
import { renderComponent, screen, cleanup } from "$lib/test-utils";
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

vi.mock("$lib/api/client", () => ({
  setUnauthorizedHandler: vi.fn(),
}));

vi.mock("$lib/stores/auth", async () => {
  const { derived, writable } = await import("svelte/store");
  const _role = writable<string | null>("admin");
  return {
    initAuth: vi.fn(),
    logoutLocal: vi.fn(),
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
