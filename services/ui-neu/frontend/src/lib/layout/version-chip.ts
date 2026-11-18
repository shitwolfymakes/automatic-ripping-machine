import type { SystemVersionResponse } from '$lib/types/api.gen';

export type VersionChipState = 'up-to-date' | 'update' | 'version-only';

export interface VersionChipView {
	version: string;
	state: VersionChipState;
	releaseUrl: string;
	latestVersion: string;
	/** Where the whole chip links. */
	href: string;
	/** The chip link's accessible name. */
	label: string;
}

export const DEFAULT_REPO_URL = 'https://github.com/automatic-ripping-machine/automatic-ripping-machine';

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
	const version = withV(resp.version);
	const state = chipState(resp);
	const releaseUrl = resp.release_url ?? '';
	const latestVersion = resp.latest_version ?? '';
	const update = state === 'update';
	return {
		version,
		state,
		releaseUrl,
		latestVersion,
		href: update ? releaseUrl : (resp.repo_url ?? DEFAULT_REPO_URL),
		label: update
			? `Update available: ${withV(latestVersion)} (opens in a new tab)`
			: `ARM ${version} on GitHub (opens in a new tab)`
	};
}
