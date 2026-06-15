import type { DriveView, DriveUpdateRequest, DriveDiagnosticResponse, DriveRescanResponse } from '$lib/types/api.gen';
import { get, patch, del, post, buildQuery } from './client';
import { notAvailable } from './_stub';

export function fetchDrives(): Promise<DriveView[]> {
	return get<DriveView[]>('/api/drives');
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

// MISSING in v3 (no per-drive scan/eject endpoint) — screens guarded off.
export async function scanDrive(_driveId: string): Promise<never> {
	notAvailable('Drive scan');
}

export async function ejectDrive(_driveId: string, _method?: string): Promise<never> {
	notAvailable('Drive eject');
}
