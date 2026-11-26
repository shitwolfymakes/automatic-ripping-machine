import { notAvailable } from './_stub';
import { get, post } from './client';

// Orphan folder cleanup and transcoder job cleanup have no v3 backend. The Files
// page hides them behind features.maintenance, and these stubs reject before any
// fetch. The image-cache endpoints are real.
//
// The shapes the (dormant) maintenance UI reads are declared locally here and
// re-exported under the names the pages import.

interface OrphanFolderEntry {
	path: string;
	name: string;
	size_bytes: number;
	category: string;
}

interface OrphanFolderList {
	folders: OrphanFolderEntry[];
	roots?: string[];
	total_size_bytes?: number;
}

interface MaintenanceDeleteResult {
	success: boolean;
	path: string;
}

interface MaintenanceBulkDeleteResult {
	removed: string[];
	errors: string[];
}

interface CleanupTranscoderResult {
	deleted: number;
	errors: string[];
}

export interface ImageCacheStats {
	count: number;
	size_mb: number;
	cleared?: number;
	freed_bytes?: number;
}

// Alias kept for the pages that still import the old response name.
export type OrphanFoldersResponse = OrphanFolderList;

export async function fetchOrphanFolders(): Promise<OrphanFolderList> {
	notAvailable('Orphan folders');
}

export async function deleteFolder(_path: string): Promise<MaintenanceDeleteResult> {
	notAvailable('Maintenance delete folder');
}

export async function bulkDeleteFolders(_paths: string[]): Promise<MaintenanceBulkDeleteResult> {
	notAvailable('Maintenance bulk-delete folders');
}

export async function cleanupTranscoder(): Promise<CleanupTranscoderResult> {
	notAvailable('Cleanup transcoder');
}

export function fetchImageCacheStats(): Promise<ImageCacheStats> {
	return get<ImageCacheStats>('/api/images/cache');
}

export function clearImageCache(): Promise<ImageCacheStats> {
	return post<ImageCacheStats>('/api/images/cache/clear');
}
