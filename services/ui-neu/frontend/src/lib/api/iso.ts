import type { IsoLibraryListing, IsoRipCreated, IsoRipRequest } from '$lib/types/api.gen';
import { get, post, del, buildQuery } from './client';

export function fetchIsoLibrary(subpath = ''): Promise<IsoLibraryListing> {
	return get<IsoLibraryListing>(`/api/iso/library${buildQuery({ subpath: subpath || undefined })}`);
}

export function startIsoRip(path: string, sessionId?: string | null): Promise<IsoRipCreated> {
	const body: IsoRipRequest = { path, session_id: sessionId || null };
	return post<IsoRipCreated>('/api/iso/rips', body);
}

export function cancelIsoRip(driveId: string): Promise<void> {
	return del(`/api/iso/rips/${driveId}`);
}
