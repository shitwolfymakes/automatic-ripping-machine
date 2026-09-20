import { describe, it, expect, vi, beforeEach } from "vitest";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

function jsonResponse(data: unknown, ok = true) {
  return {
    ok,
    status: ok ? 200 : 500,
    statusText: ok ? "OK" : "Error",
    json: () => Promise.resolve(data),
  };
}

import {
  fetchRoots,
  fetchDirectory,
  renameFile,
  moveFile,
  createDirectory,
  fixPermissions,
  deleteFile,
} from "../api/files";

beforeEach(() => mockFetch.mockReset());

describe("fetchRoots", () => {
  it("GETs /api/files/roots", async () => {
    const roots = [
      { key: "media", label: "Media", path: "/media", writable: true },
    ];
    mockFetch.mockResolvedValue(jsonResponse(roots));
    const result = await fetchRoots();
    expect(result).toEqual(roots);
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/files/roots",
      expect.objectContaining({ method: "GET" }),
    );
  });
});

describe("fetchDirectory", () => {
  it("GETs /api/files/list with root and subpath query params", async () => {
    const listing = {
      root: "media",
      subpath: "movies",
      readonly: false,
      entries: [],
    };
    mockFetch.mockResolvedValue(jsonResponse(listing));
    const result = await fetchDirectory("media", "movies");
    expect(result).toEqual(listing);
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/files/list?root=media&subpath=movies",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("GETs /api/files/list with empty subpath by default", async () => {
    const listing = {
      root: "media",
      subpath: "",
      readonly: false,
      entries: [],
    };
    mockFetch.mockResolvedValue(jsonResponse(listing));
    await fetchDirectory("media");
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/files/list?root=media&subpath=",
      expect.objectContaining({ method: "GET" }),
    );
  });
});

describe("createDirectory", () => {
  it("POSTs /api/files/mkdir with root, subpath, name", async () => {
    const response = { root: "media", subpath: "movies/new-dir" };
    mockFetch.mockResolvedValue(jsonResponse(response));
    const result = await createDirectory("media", "movies", "new-dir");
    expect(result).toEqual(response);
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/files/mkdir",
      expect.objectContaining({ method: "POST" }),
    );
    const init = mockFetch.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({
      root: "media",
      subpath: "movies",
      name: "new-dir",
    });
  });
});

describe("renameFile", () => {
  it("POSTs /api/files/rename with root, subpath, new_name", async () => {
    const response = { root: "media", subpath: "movies/renamed.mkv" };
    mockFetch.mockResolvedValue(jsonResponse(response));
    const result = await renameFile("media", "movies/old.mkv", "renamed.mkv");
    expect(result).toEqual(response);
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/files/rename",
      expect.objectContaining({ method: "POST" }),
    );
    const init = mockFetch.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({
      root: "media",
      subpath: "movies/old.mkv",
      new_name: "renamed.mkv",
    });
  });
});

describe("moveFile", () => {
  it("POSTs /api/files/move with root, subpath, dest_root, dest_subpath", async () => {
    const response = { root: "archive", subpath: "movies/file.mkv" };
    mockFetch.mockResolvedValue(jsonResponse(response));
    const result = await moveFile(
      "media",
      "movies/file.mkv",
      "archive",
      "movies",
    );
    expect(result).toEqual(response);
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/files/move",
      expect.objectContaining({ method: "POST" }),
    );
    const init = mockFetch.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({
      root: "media",
      subpath: "movies/file.mkv",
      dest_root: "archive",
      dest_subpath: "movies",
    });
  });
});

describe("fixPermissions", () => {
  it("POSTs /api/files/fix-permissions with root and subpath", async () => {
    const response = { fixed: 3 };
    mockFetch.mockResolvedValue(jsonResponse(response));
    const result = await fixPermissions("media", "movies");
    expect(result).toEqual(response);
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/files/fix-permissions",
      expect.objectContaining({ method: "POST" }),
    );
    const init = mockFetch.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({
      root: "media",
      subpath: "movies",
    });
  });
});

describe("deleteFile", () => {
  it("DELETEs /api/files with root and subpath query params", async () => {
    const response = { deleted: true };
    mockFetch.mockResolvedValue(jsonResponse(response));
    const result = await deleteFile("media", "movies/file.mkv");
    expect(result).toEqual(response);
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/files?root=media&subpath=movies%2Ffile.mkv",
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});
