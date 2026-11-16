import type { SystemVersionResponse } from '$lib/types/api.gen';

export type VersionChipState = 'up-to-date' | 'update' | 'version-only';

export interface VersionChipView {
	version: string;
	state: VersionChipState;
	releaseUrl: string;
	latestVersion: string;
}

/** Prefix a single leading "v" without doubling an existing one. */
export function withV(version: string): string {
	return version.startsWith('v') ? version : `v${version}`;
}

function chipState(resp: SystemVersionResponse): VersionChipState {
	if (resp.update_available === true && resp.release_url && resp.latest_version) return 'update';
	if (resp.update_available === false && resp.latest_version) return 'up-to-date';
	return 'version-only';
}

/** Decide what the sidebar version chip shows; null means the version fetch failed. */
export function versionChipView(resp: SystemVersionResponse | null): VersionChipView | null {
	if (!resp) return null;
	return {
		version: withV(resp.version),
		state: chipState(resp),
		releaseUrl: resp.release_url ?? '',
		latestVersion: resp.latest_version ?? ''
	};
}
