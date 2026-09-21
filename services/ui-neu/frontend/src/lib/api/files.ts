import type {
  DirectoryListing,
  FileEntry,
  FilePathResponse,
  FileRoot,
  FixPermsResponse,
} from "$lib/types/api.gen";
import { del, get, post } from "./client";

export type {
  DirectoryListing,
  FileEntry,
  FilePathResponse,
  FileRoot,
  FixPermsResponse,
};

// v3 filesystem browser — GET /api/files/roots, /api/files/list, POST /api/files/mkdir,
// /api/files/rename, /api/files/move, /api/files/fix-permissions, DELETE /api/files.

export function fetchRoots(): Promise<FileRoot[]> {
  return get<FileRoot[]>("/api/files/roots");
}

export function fetchDirectory(
  root: string,
  subpath = "",
): Promise<DirectoryListing> {
  return get<DirectoryListing>(
    `/api/files/list?root=${encodeURIComponent(root)}&subpath=${encodeURIComponent(subpath)}`,
  );
}

export function createDirectory(
  root: string,
  subpath: string,
  name: string,
): Promise<FilePathResponse> {
  return post<FilePathResponse>("/api/files/mkdir", { root, subpath, name });
}

export function renameFile(
  root: string,
  subpath: string,
  new_name: string,
): Promise<FilePathResponse> {
  return post<FilePathResponse>("/api/files/rename", {
    root,
    subpath,
    new_name,
  });
}

export function moveFile(
  root: string,
  subpath: string,
  dest_root: string,
  dest_subpath: string,
): Promise<FilePathResponse> {
  return post<FilePathResponse>("/api/files/move", {
    root,
    subpath,
    dest_root,
    dest_subpath,
  });
}

export function fixPermissions(
  root: string,
  subpath: string,
): Promise<FixPermsResponse> {
  return post<FixPermsResponse>("/api/files/fix-permissions", {
    root,
    subpath,
  });
}

export function deleteFile(
  root: string,
  subpath: string,
): Promise<{ [key: string]: boolean }> {
  return del<{ [key: string]: boolean }>(
    `/api/files?root=${encodeURIComponent(root)}&subpath=${encodeURIComponent(subpath)}`,
  );
}
