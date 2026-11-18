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

/** How long the sidebar waits for the version before drawing the panel without the chip. */
export const VERSION_CHIP_TIMEOUT_MS = 5000;

/** Only a GitHub page becomes the chip's link target. */
function isGithubPage(url: string | null | undefined): url is string {
	return typeof url === 'string' && url.startsWith('https://github.com/');
}

/** What `load` returns, or null when it throws, rejects or has not settled within `ms`. */
export function withinTimeout<T>(load: () => Promise<T>, ms: number): Promise<T | null> {
	return new Promise((resolve) => {
		const timer = setTimeout(() => resolve(null), ms);
		Promise.resolve()
			.then(load)
			.then(
				(value) => {
					clearTimeout(timer);
					resolve(value);
				},
				() => {
					clearTimeout(timer);
					resolve(null);
				}
			);
	});
}

/** Prefix a single leading "v" without doubling an existing one. */
export function withV(version: string): string {
	return version.startsWith('v') ? version : `v${version}`;
}

function chipState(resp: SystemVersionResponse): VersionChipState {
	if (resp.update_available === true && isGithubPage(resp.release_url) && resp.latest_version) return 'update';
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
		href: update ? releaseUrl : isGithubPage(resp.repo_url) ? resp.repo_url : DEFAULT_REPO_URL,
		label: update
			? `Update available: ${withV(latestVersion)} (opens in a new tab)`
			: `ARM ${version} on GitHub (opens in a new tab)`
	};
}
