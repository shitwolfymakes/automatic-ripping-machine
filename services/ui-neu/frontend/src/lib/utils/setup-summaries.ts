import type { ConfigView, DriveView, GpuView, SetupView } from '$lib/types/api.gen';
import { effectiveMovieProvider, providerLabel } from '$lib/utils/search-providers';
import { plural } from '$lib/utils/plural';

const LOOKUP_KEYS = ['tmdb_api_key', 'omdb_api_key', 'tvdb_api_key'] as const satisfies readonly (keyof ConfigView)[];

/** What the Finish step's summary lines are worked out from. */
export interface SummaryInputs {
	view: SetupView;
	drives: DriveView[];
	config: ConfigView | null;
	gpus: GpuView[];
	channelCount: number;
	transcoderEnabled: boolean;
}

function countOf(n: number, noun: string): string {
	return `${n} ${plural(n, noun)}`;
}

/** The enrolled and ignored drive counts for the Drives line. */
export function drivesSummary(drives: DriveView[]): string {
	const enrolled = drives.filter((d) => d.lifecycle === 'enrolled' && d.kind !== 'virtual').length;
	const ignored = drives.filter((d) => d.lifecycle === 'ignored').length;
	return `${enrolled} enrolled, ${ignored} ignored`;
}

/** The System line: a fix is needed, or all checks pass. */
export function systemSummary(view: SetupView): string {
	return view.progress.system?.state === 'attention'
		? 'Needs a fix on the server, see System check.'
		: 'All checks pass.';
}

/** The Notifications line: the channel count, or inbox only. */
export function notificationsSummary(channelCount: number): string {
	return channelCount ? countOf(channelCount, 'channel') : 'Inbox only';
}

/** The MakeMKV line: which key is in use and whether it is valid. */
export function makemkvSummary(config: ConfigView): string {
	return `${config.makemkv_key ? 'Purchased key' : 'Free beta key'}${config.makemkv_key_valid ? ', valid' : ''}`;
}

/** The Metadata line: saved lookup keys and the provider titles are looked up with. */
export function metadataSummary(config: ConfigView): string {
	const keys = LOOKUP_KEYS.filter((k) => !!config[k]).length;
	// The provider the backend will actually search with, not the raw
	// setting: an unkeyed choice falls back, and a TVDb-only install has
	// no movie provider at all (see effectiveMovieProvider).
	const movieProvider = effectiveMovieProvider(config);
	const lookedUpWith = movieProvider ? ` Titles looked up with ${providerLabel(movieProvider)}.` : '';
	return keys ? `${countOf(keys, 'key')} saved.${lookedUpWith}` : 'No lookup key yet';
}

/** The Discs line: manual, review first, or fully automatic. */
export function discsSummary(config: ConfigView): string {
	if (!config.auto_rip_on_insert) return 'Manual';
	return config.hold_for_review ? 'Review first' : 'Fully automatic';
}

/** The Transcoding line: ripper only, graphics devices enabled, or CPU encoding. */
export function transcodingSummary(transcoderEnabled: boolean, gpus: GpuView[]): string {
	if (!transcoderEnabled) return 'Ripper only';
	const enabledGpus = gpus.filter((g) => g.enabled).length;
	return enabledGpus ? `${countOf(enabledGpus, 'graphics device')} enabled` : 'CPU encoding';
}

/** The summary line for each step that has one, keyed by step id. */
export function setupSummaries(inputs: SummaryInputs): Record<string, string> {
	const { view, drives, config, gpus, channelCount, transcoderEnabled } = inputs;
	const out: Record<string, string> = {
		account: 'Password changed.',
		system: systemSummary(view),
		drives: drivesSummary(drives),
		notifications: notificationsSummary(channelCount)
	};
	if (config) {
		out.makemkv = makemkvSummary(config);
		out.metadata = metadataSummary(config);
		out.discs = discsSummary(config);
	}
	out.transcoding = transcodingSummary(transcoderEnabled, gpus);
	return out;
}
