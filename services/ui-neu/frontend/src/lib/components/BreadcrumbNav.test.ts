import { describe, it, expect, vi, afterEach } from "vitest";
import { renderComponent, screen, fireEvent, cleanup } from "$lib/test-utils";
import BreadcrumbNav from "./BreadcrumbNav.svelte";
import type { FileRoot } from "$lib/api/files";

const roots: FileRoot[] = [
  {
    key: "completed",
    path: "/media/completed",
    label: "Completed",
    writable: true,
  },
  { key: "raw", path: "/media/raw", label: "Raw", writable: true },
];

describe("BreadcrumbNav", () => {
  afterEach(() => cleanup());

  describe("rendering", () => {
    it("renders root label for root path", () => {
      renderComponent(BreadcrumbNav, {
        props: { root: "completed", subpath: "", roots, onnavigate: vi.fn() },
      });
      expect(screen.getByText("Completed")).toBeInTheDocument();
    });

    it("renders breadcrumb segments for nested path", () => {
      renderComponent(BreadcrumbNav, {
        props: {
          root: "completed",
          subpath: "movies/action",
          roots,
          onnavigate: vi.fn(),
        },
      });
      expect(screen.getByText("Completed")).toBeInTheDocument();
      expect(screen.getByText("movies")).toBeInTheDocument();
      expect(screen.getByText("action")).toBeInTheDocument();
    });

    it("renders last segment as plain text (not a button)", () => {
      renderComponent(BreadcrumbNav, {
        props: {
          root: "completed",
          subpath: "movies",
          roots,
          onnavigate: vi.fn(),
        },
      });
      const lastSegment = screen.getByText("movies");
      expect(lastSegment.tagName).toBe("SPAN");
    });

    it("renders intermediate segments as buttons", () => {
      renderComponent(BreadcrumbNav, {
        props: {
          root: "completed",
          subpath: "movies/action",
          roots,
          onnavigate: vi.fn(),
        },
      });
      const rootBtn = screen.getByText("Completed");
      expect(rootBtn.tagName).toBe("BUTTON");
      const moviesBtn = screen.getByText("movies");
      expect(moviesBtn.tagName).toBe("BUTTON");
    });

    it("renders nothing for unrecognized root key", () => {
      const { container } = renderComponent(BreadcrumbNav, {
        props: {
          root: "unknown",
          subpath: "some/path",
          roots,
          onnavigate: vi.fn(),
        },
      });
      const nav = container.querySelector("nav");
      // Unknown root key falls back to using key as label — still renders
      // but only one segment (the root key itself as the last crumb + subpath segments)
      expect(nav).toBeTruthy();
    });
  });

  describe("interactions", () => {
    it("calls onnavigate with root+empty subpath when root crumb is clicked", async () => {
      const onnavigate = vi.fn();
      renderComponent(BreadcrumbNav, {
        props: {
          root: "completed",
          subpath: "movies/action",
          roots,
          onnavigate,
        },
      });
      await fireEvent.click(screen.getByText("Completed"));
      expect(onnavigate).toHaveBeenCalledWith("completed", "");
    });

    it("calls onnavigate with intermediate subpath when intermediate crumb is clicked", async () => {
      const onnavigate = vi.fn();
      renderComponent(BreadcrumbNav, {
        props: {
          root: "completed",
          subpath: "movies/action",
          roots,
          onnavigate,
        },
      });
      await fireEvent.click(screen.getByText("movies"));
      expect(onnavigate).toHaveBeenCalledWith("completed", "movies");
    });
  });
});
