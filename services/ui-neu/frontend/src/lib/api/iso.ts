import type {
	IsoFolderListing,
	IsoLibraryListing,
	IsoPrepareView,
	IsoRipCreated,
	IsoRipRequest
} from '$lib/types/api.gen';
import { get, post, del, buildQuery } from './client';

export function fetchIsoLibrary(subpath = ''): Promise<IsoLibraryListing> {
	return get<IsoLibraryListing>(`/api/iso/library${buildQuery({ subpath: subpath || undefined })}`);
}

/** Every disc folder (BDMV / VIDEO_TS) in the library, flat, for "Rip from folder". */
export function fetchIsoFolders(): Promise<IsoFolderListing> {
	return get<IsoFolderListing>('/api/iso/folders');
}

/** Start a rip of an .iso file or a disc folder (`path` is library-relative). */
export function startIsoRip(path: string, sessionId?: string | null): Promise<IsoRipCreated> {
	const body: IsoRipRequest = { path, session_id: sessionId || null };
	return post<IsoRipCreated>('/api/iso/rips', body);
}

export function cancelIsoRip(driveId: string): Promise<void> {
	return del(`/api/iso/rips/${driveId}`);
}

/** ISO rips whose ripper is still scanning or unpacking the image (no job yet). */
export function fetchIsoPreparing(): Promise<IsoPrepareView[]> {
	return get<IsoPrepareView[]>('/api/iso/rips/preparing');
}
