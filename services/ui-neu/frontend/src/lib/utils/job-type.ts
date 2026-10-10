// The five video-type hues (blue/purple/green/amber/cyan) plus a neutral
// fallback have no five-tone block in the vocabulary (spec 5.1 has four
// tones: danger/warning/success/info). Movie/Music/Data map onto the
// nearest existing tone (info/success/warning); Series and the unidentified
// Video fallback have no tone at all, so they take the fixed accent tokens
// (accent-3 violet, accent-4 cyan) the disc-type icons already use. Each
// config now carries CSS custom-property VALUES (not Tailwind classes):
// consumers bind them via `style:--jt-*` and a shared scoped/`badge`-family
// rule reads the vars, so no component hand-rolls its own colour switch.
export interface VideoTypeConfig {
	label: string;
	icon: string;
	badgeBg: string;
	badgeText: string;
	placeholderBg: string;
	placeholderText: string;
	accent: string;
	iconColor: string;
}

const MOVIE_CONFIG: VideoTypeConfig = {
	label: 'Movie',
	icon: 'clapperboard',
	badgeBg: 'var(--color-info-soft)',
	badgeText: 'var(--color-on-info-soft)',
	placeholderBg: 'var(--color-info-soft)',
	placeholderText: 'var(--color-info)',
	accent: 'var(--color-info)',
	iconColor: 'var(--color-info)',
};

const SERIES_CONFIG: VideoTypeConfig = {
	label: 'Series',
	icon: 'tv',
	badgeBg: 'color-mix(in srgb, var(--color-accent-3) 30%, transparent)',
	badgeText: 'var(--color-accent-3)',
	placeholderBg: 'color-mix(in srgb, var(--color-accent-3) 30%, transparent)',
	placeholderText: 'var(--color-accent-3)',
	accent: 'var(--color-accent-3)',
	iconColor: 'var(--color-accent-3)',
};

const MUSIC_CONFIG: VideoTypeConfig = {
	label: 'Music',
	icon: 'music',
	badgeBg: 'var(--color-success-soft)',
	badgeText: 'var(--color-on-success-soft)',
	placeholderBg: 'var(--color-success-soft)',
	placeholderText: 'var(--color-success)',
	accent: 'var(--color-success)',
	iconColor: 'var(--color-success)',
};

const DATA_CONFIG: VideoTypeConfig = {
	label: 'Data',
	icon: 'database',
	badgeBg: 'var(--color-warning-soft)',
	badgeText: 'var(--color-on-warning-soft)',
	placeholderBg: 'var(--color-warning-soft)',
	placeholderText: 'var(--color-warning)',
	accent: 'var(--color-warning)',
	iconColor: 'var(--color-warning)',
};

// Unidentified video disc: ARM knows it's a DVD/Blu-ray/UHD but
// hasn't classified it as movie/series yet. Cyan reads "informational"
// without colliding with Movie (blue), Series (purple), or Data (amber).
const VIDEO_FALLBACK_CONFIG: VideoTypeConfig = {
	label: 'Video',
	icon: 'disc',
	badgeBg: 'color-mix(in srgb, var(--color-accent-4) 30%, transparent)',
	badgeText: 'var(--color-accent-4)',
	placeholderBg: 'color-mix(in srgb, var(--color-accent-4) 30%, transparent)',
	placeholderText: 'var(--color-accent-4)',
	accent: 'var(--color-accent-4)',
	iconColor: 'var(--color-accent-4)',
};

const FALLBACK_CONFIG: VideoTypeConfig = {
	label: 'Disc',
	icon: 'disc',
	badgeBg: 'var(--color-primary-tint-2)',
	badgeText: 'var(--color-text-secondary)',
	placeholderBg: 'var(--color-primary-tint-2)',
	placeholderText: 'var(--color-text-faint)',
	accent: 'var(--color-text-faint)',
	iconColor: 'var(--color-text-muted)',
};

const TYPE_MAP: Record<string, VideoTypeConfig> = {
	movie: MOVIE_CONFIG,
	series: SERIES_CONFIG,
	music: MUSIC_CONFIG,
	data: DATA_CONFIG,
};

const VIDEO_DISCTYPES = new Set(['dvd', 'bluray', 'bluray4k', 'uhd']);

export function getVideoTypeConfig(
	videoType: string | null | undefined,
	disctype?: string | null,
): VideoTypeConfig {
	const known = videoType ? TYPE_MAP[videoType.toLowerCase()] : undefined;
	if (known) return known;
	if (disctype && VIDEO_DISCTYPES.has(disctype.toLowerCase())) {
		return VIDEO_FALLBACK_CONFIG;
	}
	return FALLBACK_CONFIG;
}

// Source of truth: v3 JobStatus (generated in `$lib/types/api.gen`).
// isJobActive() is only ever called with Job.status values
// (ActiveJobRow / JobCard / JobRow / JobActions / job-fields / jobs/[id]),
// so this set deliberately tracks JobStatus's non-terminal members and
// nothing else. Transcode-task TaskStatus ('processing', 'pending') and
// TrackStatus ('pending') are intentionally absent - they never reach
// isJobActive in current code paths.
//
// v2.0.0 disambiguation: 'ripping' split into 'video_ripping'/'audio_ripping',
// 'waiting' split into 'manual_paused'/'makemkv_throttled'. Old strings kept
// as defensive fallbacks for in-flight jobs observed mid-deploy.
const ACTIVE_STATUSES = new Set([
	// v3 JobStatus non-terminal members.
	'created',
	'awaiting_user_id',
	'identified',
	'identifying',
	'ready',
	'ripping',                  // legacy pre-v2.0.0
	'video_ripping',
	'audio_ripping',
	'copying',
	'ejecting',
	'transcoding',
	'waiting',                  // legacy pre-v2.0.0
	'manual_paused',
	'makemkv_throttled',
	'waiting_transcode',
]);

const DISC_TYPE_LABELS: Record<string, string> = {
	dvd: 'DVD',
	bluray: 'Blu-ray',
	bluray4k: '4K UHD',
	cd: 'CD',
	music: 'Music CD',
	data: 'Data',
	unknown: 'Unknown',
};

export function discTypeLabel(disctype: string | null | undefined): string {
	if (!disctype) return 'Unknown';
	return DISC_TYPE_LABELS[disctype.toLowerCase()] ?? disctype;
}

export function isJobActive(status: string | null | undefined): boolean {
	if (!status) return false;
	return ACTIVE_STATUSES.has(status.toLowerCase());
}
