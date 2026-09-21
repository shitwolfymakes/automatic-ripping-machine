import { apiFetch } from './client';
import { notAvailable } from './_stub';
import type { FileRoot, DirectoryListing } from './files';

// Folder import + ingress browser have no v3 backend (MISSING). ISO job creation
// is ripper-side and not exposed (MISSING). Only the ISO *scan* endpoint exists
// in v3 (POST /api/jobs/iso/scan). The Import wizard screen is feature-flagged
// OFF, so the MISSING calls reject before any fetch.
//
// The (dormant) wizard reads BFF-shaped scan fields that v3's IsoScanResponse
// does not carry, so the scan-result/create-request shapes are declared locally
// here and re-exported. These keep the wizard compiling without leaning on
// api.gen members that no longer exist.

export interface IsoScanResult {
	path?: string;
	title_suggestion?: string | null;
	year_suggestion?: string | null;
	disc_type?: string | null;
	stream_count?: number | null;
	label?: string | null;
	volume_id?: string | null;
	iso_size?: number | null;
}

export interface FolderScanResult {
	path?: string;
	title_suggestion?: string | null;
	year_suggestion?: string | null;
	disc_type?: string | null;
	stream_count?: number | null;
	label?: string | null;
	folder_size_bytes?: number | null;
	season?: number | null;
	disc_number?: number | null;
	disc_total?: number | null;
}

export interface IsoCreateRequest {
	source_path: string;
	title: string;
	year: string | null;
	video_type: 'movie' | 'series';
	disctype: string;
	imdb_id: string | null;
	poster_url: string | null;
	season: number | null;
	disc_number: number | null;
	disc_total: number | null;
}

export type FolderCreateRequest = IsoCreateRequest;
export interface IsoCreateResponse {
	job_id: string;
}
export type FolderCreateResponse = IsoCreateResponse;

export type { FileRoot, DirectoryListing };

// EXISTS in v3 — POST /api/jobs/iso/scan. The response is typed locally as
// IsoScanResult for the dormant wizard's field reads.
export function scanIso(path: string): Promise<IsoScanResult> {
	return apiFetch('/api/jobs/iso/scan', {
		method: 'POST',
		body: JSON.stringify({ path })
	});
}

// MISSING in v3.
export async function scanFolder(_path: string): Promise<FolderScanResult> {
	notAvailable('Folder import scan');
}

export async function createFolderJob(_data: FolderCreateRequest): Promise<FolderCreateResponse> {
	notAvailable('Folder import job creation');
}

export async function createIsoJob(_data: IsoCreateRequest): Promise<IsoCreateResponse> {
	notAvailable('ISO import job creation');
}

export async function fetchIngressDirectory(_path: string): Promise<DirectoryListing> {
	notAvailable('Ingress directory browser');
}

export async function fetchIngressRoot(): Promise<FileRoot[]> {
	notAvailable('Ingress root browser');
}
