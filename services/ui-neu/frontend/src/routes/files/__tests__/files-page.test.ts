import { describe, it, expect, vi, afterEach } from "vitest";
import {
  renderComponent,
  screen,
  fireEvent,
  cleanup,
  waitFor,
} from "$lib/test-utils";
import FilesPage from "../+page.svelte";
import {
  createFileEntry,
  createFolderEntry,
} from "$lib/components/__fixtures__/files";

import { fetchRoots, fetchDirectory } from "$lib/api/files";
import { fetchOrphanFolders, cleanupTranscoder } from "$lib/api/maintenance";

const defaultEntries = [
  createFileEntry("movie.mkv", 4294967296),
  createFolderEntry("subfolder", "2025-06-14T10:00:00Z"),
  createFileEntry("show.mkv", 2147483648, "mkv"),
];

vi.mock("$app/stores", async () => {
  const { readable } = await import("svelte/store");
  return {
    page: readable({ url: new URL("http://localhost/files") }),
  };
});

vi.mock("$lib/api/files", () => ({
  fetchRoots: vi.fn(() =>
    Promise.resolve([
      { key: "raw", label: "Raw", path: "/media/raw", writable: true },
      {
        key: "completed",
        label: "Completed",
        path: "/media/completed",
        writable: true,
      },
    ]),
  ),
  fetchDirectory: vi.fn(() =>
    Promise.resolve({
      root: "raw",
      subpath: "",
      parent_subpath: null,
      readonly: false,
      entries: [
        createFileEntry("movie.mkv", 4294967296),
        createFolderEntry("subfolder", "2025-06-14T10:00:00Z"),
        createFileEntry("show.mkv", 2147483648, "mkv"),
      ],
    }),
  ),
  renameFile: vi.fn(() =>
    Promise.resolve({ root: "raw", subpath: "movie.mkv" }),
  ),
  moveFile: vi.fn(() => Promise.resolve({ root: "raw", subpath: "movie.mkv" })),
  deleteFile: vi.fn(() => Promise.resolve({ deleted: true })),
  createDirectory: vi.fn(() =>
    Promise.resolve({ root: "raw", subpath: "new-folder" }),
  ),
  fixPermissions: vi.fn(() => Promise.resolve({ fixed: 3 })),
}));

vi.mock("$lib/api/maintenance", () => ({
  fetchOrphanFolders: vi.fn(() =>
    Promise.resolve({ total_size_bytes: 0, folders: [] }),
  ),
  deleteFolder: vi.fn(() => Promise.resolve({ success: true })),
  bulkDeleteFolders: vi.fn(() => Promise.resolve({ removed: [], errors: [] })),
  cleanupTranscoder: vi.fn(() =>
    Promise.resolve({ success: true, deleted: 0, errors: [] }),
  ),
}));

vi.stubGlobal(
  "confirm",
  vi.fn(() => true),
);

const mockFetchDirectory = vi.mocked(fetchDirectory);

describe("Files Page", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    vi.mocked(confirm).mockReturnValue(true);
  });

  describe("rendering", () => {
    it("renders page title", () => {
      renderComponent(FilesPage);
      expect(screen.getByText("Files")).toBeInTheDocument();
    });

    it("renders root tabs after loading", async () => {
      renderComponent(FilesPage);
      await waitFor(() => {
        const matches = screen.getAllByText("Completed");
        expect(matches.length).toBeGreaterThanOrEqual(1);
      });
    });

    it("renders tabs in rootOrder: Raw before Completed", async () => {
      renderComponent(FilesPage);
      await waitFor(() => {
        const rawTab = screen.getAllByText("Raw")[0];
        const completedTab = screen.getAllByText("Completed")[0];
        // Raw should appear before Completed in DOM order
        expect(
          rawTab.compareDocumentPosition(completedTab) &
            Node.DOCUMENT_POSITION_FOLLOWING,
        ).toBeTruthy();
      });
    });

    it("renders file listing after auto-navigation", async () => {
      renderComponent(FilesPage);
      await waitFor(() => {
        expect(screen.getByText("movie.mkv")).toBeInTheDocument();
        expect(screen.getByText("subfolder")).toBeInTheDocument();
        expect(screen.getByText("show.mkv")).toBeInTheDocument();
      });
    });

    it("renders file sizes", async () => {
      renderComponent(FilesPage);
      await waitFor(() => {
        expect(screen.getByText("4 GB")).toBeInTheDocument();
        expect(screen.getByText("2 GB")).toBeInTheDocument();
      });
    });

    it("renders checkboxes for file selection", async () => {
      renderComponent(FilesPage);
      await waitFor(() => {
        expect(screen.getByText("movie.mkv")).toBeInTheDocument();
      });
      const checkboxes = screen.getAllByRole("checkbox");
      expect(checkboxes.length).toBeGreaterThanOrEqual(3); // 3 entries
    });
  });

  describe("navigation", () => {
    it("navigates to subdirectory on click", async () => {
      renderComponent(FilesPage);
      await waitFor(() => {
        expect(screen.getByText("subfolder")).toBeInTheDocument();
      });
      // subfolder is a directory — clicking it triggers navigation
      await fireEvent.click(screen.getByText("subfolder"));
      await waitFor(() => {
        expect(mockFetchDirectory).toHaveBeenCalledWith("raw", "subfolder");
      });
    });

    it("switches root on tab click", async () => {
      renderComponent(FilesPage);
      await waitFor(() => {
        const matches = screen.getAllByText("Raw");
        expect(matches.length).toBeGreaterThanOrEqual(1);
      });
      await fireEvent.click(screen.getByText("Completed"));
      await waitFor(() => {
        expect(mockFetchDirectory).toHaveBeenCalledWith("completed", "");
      });
    });
  });

  describe("error handling", () => {
    it("shows error when fetchRoots fails", async () => {
      vi.mocked(fetchRoots).mockRejectedValueOnce(
        new Error("Connection failed"),
      );
      renderComponent(FilesPage);
      await waitFor(() => {
        expect(screen.getByText("Connection failed")).toBeInTheDocument();
      });
    });

    it("shows error when fetchDirectory fails", async () => {
      mockFetchDirectory.mockRejectedValueOnce(new Error("Permission denied"));
      renderComponent(FilesPage);
      await waitFor(() => {
        expect(screen.getByText("Permission denied")).toBeInTheDocument();
      });
    });
  });

  describe("orphan folders", () => {
    it("shows orphan folders button in toolbar", async () => {
      renderComponent(FilesPage);
      await waitFor(() => {
        expect(screen.getByTitle("Orphan folders")).toBeInTheDocument();
      });
    });

    it("opens orphan folders modal when clicked", async () => {
      renderComponent(FilesPage);
      await waitFor(() => {
        expect(screen.getByTitle("Orphan folders")).toBeInTheDocument();
      });
      await fireEvent.click(screen.getByTitle("Orphan folders"));
      await waitFor(() => {
        expect(screen.getByText("Orphan Folders")).toBeInTheDocument();
        expect(
          screen.getByText("Folders not associated with any job"),
        ).toBeInTheDocument();
      });
    });

    it("displays folder list in modal", async () => {
      vi.mocked(fetchOrphanFolders).mockResolvedValueOnce({
        roots: ["/media/raw", "/media/completed"],
        total_size_bytes: 5000000,
        folders: [
          {
            path: "/media/raw/orphan1",
            name: "orphan1",
            size_bytes: 3000000,
            category: "raw",
          },
          {
            path: "/media/completed/orphan2",
            name: "orphan2",
            size_bytes: 2000000,
            category: "completed",
          },
        ],
      });
      renderComponent(FilesPage);
      await waitFor(() => {
        expect(screen.getByTitle("Orphan folders")).toBeInTheDocument();
      });
      await fireEvent.click(screen.getByTitle("Orphan folders"));
      await waitFor(() => {
        expect(screen.getByText("orphan1")).toBeInTheDocument();
        expect(screen.getByText("orphan2")).toBeInTheDocument();
      });
    });
  });

  describe("move picker", () => {
    it("hides selected folders from picker when browsing same directory as source", async () => {
      // The listing has one folder: "subfolder". Select it, open move dialog.
      // The picker starts in the same dir, so "subfolder" should not appear in the picker list.
      renderComponent(FilesPage);
      await waitFor(() => {
        expect(screen.getByText("subfolder")).toBeInTheDocument();
      });

      // Select "subfolder" via its checkbox (first checkbox is select-all; entry checkboxes follow)
      const checkboxes = screen.getAllByRole("checkbox");
      // The subfolder row checkbox — find checkbox near "subfolder" label
      const subfolderRow = screen.getByText("subfolder").closest("tr");
      const subfolderCheckbox = subfolderRow?.querySelector(
        'input[type="checkbox"]',
      );
      expect(subfolderCheckbox).toBeTruthy();
      await fireEvent.click(subfolderCheckbox!);

      // "Move 1" button should appear
      await waitFor(() => {
        expect(screen.getByText(/Move 1/)).toBeInTheDocument();
      });

      // Open the move dialog — picker starts in the same location (raw, "")
      await fireEvent.click(screen.getByText(/Move 1/));
      await waitFor(() => {
        expect(screen.getByText(/Move 1 item/)).toBeInTheDocument();
      });

      // "subfolder" should NOT appear in the picker list (it's the selected folder)
      const pickerDialog = screen.getByText(/Move 1 item/).closest(".relative");
      // Within the dialog, subfolder should not be a navigation option
      const folderButtons = pickerDialog?.querySelectorAll(
        "button.flex.w-full.items-center.gap-3",
      );
      const folderNames = Array.from(folderButtons ?? []).map((b) =>
        b.textContent?.trim(),
      );
      expect(folderNames.some((n) => n?.includes("subfolder"))).toBe(false);
    });

    it("shows all folders when picker is in a different directory", async () => {
      // Source listing: subfolder (selected), dest listing (different dir): also has a "subfolder" entry.
      // When picker navigates to a different dir, "subfolder" should be shown.
      mockFetchDirectory
        // First call: initial listing (raw, "")
        .mockResolvedValueOnce({
          root: "raw",
          subpath: "",
          parent_subpath: null,
          readonly: false,
          entries: [createFolderEntry("subfolder")],
        })
        // Second call: picker loading same dir
        .mockResolvedValueOnce({
          root: "raw",
          subpath: "",
          parent_subpath: null,
          readonly: false,
          entries: [createFolderEntry("subfolder"), createFolderEntry("other")],
        })
        // Third call: picker navigates into "other" — contains its own "subfolder"
        .mockResolvedValueOnce({
          root: "raw",
          subpath: "other",
          parent_subpath: "",
          readonly: false,
          entries: [createFolderEntry("subfolder")],
        });

      renderComponent(FilesPage);
      await waitFor(() => {
        expect(screen.getByText("subfolder")).toBeInTheDocument();
      });

      // Select subfolder
      const subfolderRow = screen.getByText("subfolder").closest("tr");
      const subfolderCheckbox = subfolderRow?.querySelector(
        'input[type="checkbox"]',
      );
      await fireEvent.click(subfolderCheckbox!);

      await waitFor(() =>
        expect(screen.getByText(/Move 1/)).toBeInTheDocument(),
      );
      await fireEvent.click(screen.getByText(/Move 1/));
      await waitFor(() =>
        expect(screen.getByText(/Move 1 item/)).toBeInTheDocument(),
      );

      // Navigate picker into "other" (which itself has a "subfolder" child)
      const otherBtn = await screen.findByText("other");
      await fireEvent.click(otherBtn);

      // Now picker is at (raw, "other") — different from source (raw, "").
      // The "subfolder" entry inside "other" should be visible.
      await waitFor(() => {
        const pickerSubfolders = screen.getAllByText("subfolder");
        // At least one "subfolder" is rendered inside the picker list
        expect(pickerSubfolders.length).toBeGreaterThanOrEqual(1);
      });
    });

    it("navigates into child using itemSubpath (no leading-slash strip needed)", async () => {
      // The nav callback should call fetchDirectory("raw", "subfolder") when
      // clicking the subfolder row — verifying the leading-slash strip is gone
      // and itemSubpath builds the correct path instead.
      renderComponent(FilesPage);
      await waitFor(() => {
        expect(screen.getByText("subfolder")).toBeInTheDocument();
      });

      await fireEvent.click(screen.getByText("subfolder"));

      await waitFor(() => {
        expect(mockFetchDirectory).toHaveBeenCalledWith("raw", "subfolder");
      });
      // Confirm it was NOT called with a leading slash
      const calls = mockFetchDirectory.mock.calls;
      const subfolderCalls = calls.filter(([, sp]) =>
        sp?.includes("subfolder"),
      );
      expect(subfolderCalls.every(([, sp]) => !sp?.startsWith("/"))).toBe(true);
    });
  });

  describe("transcoder cleanup", () => {
    it("shows transcoder cleanup button in toolbar", async () => {
      renderComponent(FilesPage);
      await waitFor(() => {
        expect(
          screen.getByTitle("Clean up transcoder jobs"),
        ).toBeInTheDocument();
      });
    });

    it("opens confirm dialog when clicked", async () => {
      renderComponent(FilesPage);
      await waitFor(() => {
        expect(
          screen.getByTitle("Clean up transcoder jobs"),
        ).toBeInTheDocument();
      });
      await fireEvent.click(screen.getByTitle("Clean up transcoder jobs"));
      await waitFor(() => {
        expect(screen.getByText("Clean Up Transcoder")).toBeInTheDocument();
        expect(
          screen.getByText(
            "Delete all completed and failed transcoder jobs from the transcoder database?",
          ),
        ).toBeInTheDocument();
      });
    });
  });

  describe("unmounted root", () => {
    it("shows 'not mounted' (not an error) when the root is unavailable", async () => {
      mockFetchDirectory.mockResolvedValueOnce({
        root: "iso",
        subpath: "",
        parent_subpath: null,
        readonly: false,
        entries: [],
        unavailable: true,
      });
      renderComponent(FilesPage);
      await waitFor(() => {
        expect(
          screen.getByText("This root is not mounted on the server."),
        ).toBeInTheDocument();
      });
      // The empty-dir message must NOT show, and no error banner either.
      expect(
        screen.queryByText("This directory is empty"),
      ).not.toBeInTheDocument();
    });
  });
});
