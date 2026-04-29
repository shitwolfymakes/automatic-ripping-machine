import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useAuthStore } from "../stores/auth";
import { router } from "../router";

describe("router guards", () => {
  beforeEach(async () => {
    setActivePinia(createPinia());
    localStorage.clear();
    // Reset router by replacing.
    await router.replace("/login");
  });

  it("anonymous user trying to hit /jobs is redirected to /login", async () => {
    await router.push("/jobs");
    expect(router.currentRoute.value.path).toBe("/login");
  });

  it("authenticated user with password_must_change is forced to /change-password", async () => {
    const auth = useAuthStore();
    auth.hydrate();
    auth.token = "aaa.bbb.ccc";
    auth.passwordMustChange = true;
    await router.push("/jobs");
    expect(router.currentRoute.value.path).toBe("/change-password");
  });

  it("authenticated user without must-change can navigate to /jobs", async () => {
    const auth = useAuthStore();
    auth.hydrate();
    auth.token = "aaa.bbb.ccc";
    auth.passwordMustChange = false;
    await router.push("/jobs");
    expect(router.currentRoute.value.path).toBe("/jobs");
  });

  it("/login bounces an authenticated user to /jobs", async () => {
    const auth = useAuthStore();
    auth.hydrate();
    auth.token = "aaa.bbb.ccc";
    auth.passwordMustChange = false;
    // Start somewhere else so /login is a real navigation (vue-router collapses
    // same-route navigations and skips guards otherwise).
    await router.push("/jobs");
    await router.push("/login");
    expect(router.currentRoute.value.path).toBe("/jobs");
  });
});
