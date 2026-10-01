import type { DriveView, DriveUpdateRequest, DriveDiagnosticResponse, DriveRescanResponse } from '$lib/types/api.gen';
import { get, patch, del, post, buildQuery } from './client';

// `includeRetired` adds retired rows (finished ISO rips): only the
// dashboard's drive-name map needs them, so a finished job keeps its label.
export function fetchDrives(opts: { includeRetired?: boolean } = {}): Promise<DriveView[]> {
	return get<DriveView[]>(`/api/drives${buildQuery({ include_retired: opts.includeRetired || undefined })}`);
}

export function updateDrive(driveId: string, data: DriveUpdateRequest): Promise<DriveView> {
	return patch<DriveView>(`/api/drives/${driveId}`, data);
}

export function deleteDrive(driveId: string): Promise<void> {
	return del(`/api/drives/${driveId}`);
}

export function rescanDrives(force = false): Promise<DriveRescanResponse> {
	return post<DriveRescanResponse>(`/api/drives/rescan${buildQuery({ force: force || undefined })}`);
}

export function fetchDriveDiagnostic(): Promise<DriveDiagnosticResponse> {
	return get<DriveDiagnosticResponse>('/api/drives/diagnostic');
}

export function enrollDrive(driveId: string): Promise<DriveView> {
	return post<DriveView>(`/api/drives/${driveId}/enroll`);
}

export function ignoreDrive(driveId: string): Promise<DriveView> {
	return post<DriveView>(`/api/drives/${driveId}/ignore`);
}

export function unignoreDrive(driveId: string): Promise<DriveView> {
	return post<DriveView>(`/api/drives/${driveId}/unignore`);
}

/** May answer 204 (row deleted — the drive was absent) or 200. Callers refetch. */
export function unenrollDrive(driveId: string): Promise<void> {
	return post<void>(`/api/drives/${driveId}/unenroll`);
}
