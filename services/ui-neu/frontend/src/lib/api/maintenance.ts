import { notAvailable } from './_stub';
import { get, post } from './client';

// Orphan cleanup / maintenance has no v3 backend (ALL MISSING). The orphan-logs
// and orphan-folders modals and the transcoder/image-cache cleanup actions are
// dormant, so these stubs reject before any fetch.
//
// The shapes the (dormant) maintenance UI reads are declared locally here and
// re-exported under the names the pages import; api.gen no longer carries them.

export interface OrphanLogEntry {
	path: string;
	relative_path: string;
	size_bytes: number;
}

export interface OrphanFolderEntry {
	path: string;
	name: string;
	size_bytes: number;
	category: string;
}

export interface OrphanLogList {
	files: OrphanLogEntry[];
	root?: string;
	total_size_bytes?: number;
}

export interface OrphanFolderList {
	folders: OrphanFolderEntry[];
	roots?: string[];
	total_size_bytes?: number;
}

export interface MaintenanceSummary {
	orphan_logs: number;
	orphan_folders: number;
}

export interface MaintenanceDeleteResult {
	success: boolean;
	path: string;
}

export interface MaintenanceBulkDeleteResult {
	removed: string[];
	errors: string[];
}

export interface CleanupTranscoderResult {
	deleted: number;
	errors: string[];
}

export interface ImageCacheStats {
	count: number;
	size_mb: number;
	cleared?: number;
	freed_bytes?: number;
}

export interface ClearRawResult {
	cleared: number;
	freed_bytes: number;
	path: string;
}

// Legacy aliases — the surrounding pages import these names.
export type OrphanLog = OrphanLogEntry;
export type OrphanFolder = OrphanFolderEntry;
export type OrphanLogsResponse = OrphanLogList;
export type OrphanFoldersResponse = OrphanFolderList;
export type DeleteResult = MaintenanceDeleteResult;
export type BulkDeleteResult = MaintenanceBulkDeleteResult;

export async function fetchSummary(): Promise<MaintenanceSummary> {
	notAvailable('Maintenance summary');
}

export async function fetchOrphanLogs(): Promise<OrphanLogList> {
	notAvailable('Orphan logs');
}

export async function fetchOrphanFolders(): Promise<OrphanFolderList> {
	notAvailable('Orphan folders');
}

export async function deleteLog(_path: string): Promise<MaintenanceDeleteResult> {
	notAvailable('Maintenance delete log');
}

export async function deleteFolder(_path: string): Promise<MaintenanceDeleteResult> {
	notAvailable('Maintenance delete folder');
}

export async function bulkDeleteLogs(_paths: string[]): Promise<MaintenanceBulkDeleteResult> {
	notAvailable('Maintenance bulk-delete logs');
}

export async function bulkDeleteFolders(_paths: string[]): Promise<MaintenanceBulkDeleteResult> {
	notAvailable('Maintenance bulk-delete folders');
}

export async function dismissAllNotifications(): Promise<{ success: boolean; count: number }> {
	notAvailable('Dismiss all notifications (maintenance)');
}

export async function purgeNotifications(): Promise<{ success: boolean; count: number }> {
	notAvailable('Purge notifications');
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

export async function clearRaw(): Promise<ClearRawResult> {
	notAvailable('Clear raw');
}
