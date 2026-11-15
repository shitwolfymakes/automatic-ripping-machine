// Where the HandBrake documentation explains a setting: each tab group, and each
// encoder family's card, maps to the page that covers its input values.

import type { TabId } from './fields';

const DOCS = 'https://handbrake.fr/docs/en/latest/';
const RESIZING = 'advanced/resizing-video.html';
const PRESETS_TUNES = 'technical/video-presets-tunes.html';
const FALLBACK = 'cli/command-line-reference.html';

const DIMENSIONS_PAGES: Record<string, string> = {
	Size: RESIZING,
	Orientation: RESIZING,
	Cropping: RESIZING,
	Padding: RESIZING,
	'Pixel aspect': 'technical/anamorphic-guide.html'
};

const VIDEO_PAGES: Record<string, string> = {
	'Rate control': 'technical/video-cq-vs-abr.html',
	Framerate: 'technical/frame-rates.html',
	Color: 'technical/hdr.html',
	Encoder: PRESETS_TUNES,
	Other: 'technical/video-codecs.html'
};

const AUDIO_SUBTITLE_PAGE = 'advanced/audio-subtitle-defaults.html';

// The page for a whole tab, or null when the tab's page depends on the group.
const TAB_PAGES: Partial<Record<TabId, string>> = {
	filters: 'technical/filters-summary.html',
	audio: AUDIO_SUBTITLE_PAGE,
	subtitles: AUDIO_SUBTITLE_PAGE,
	chapters: 'advanced/chapter-markers.html',
	summary: 'advanced/metadata-passthru.html'
};

const GROUP_PAGES: Partial<Record<TabId, Record<string, string>>> = {
	dimensions: DIMENSIONS_PAGES,
	video: VIDEO_PAGES
};

export function docUrlFor(tab: TabId, group: string): string {
	return DOCS + (TAB_PAGES[tab] ?? GROUP_PAGES[tab]?.[group] ?? FALLBACK);
}

// Encoder family ids start with the hardware family: nvenc_h264, qsv_av1, vce_h265.
const FAMILY_PAGES: Array<[RegExp, string]> = [
	[/^nvenc/, 'technical/video-nvenc.html'],
	[/^qsv/, 'technical/video-qsv.html'],
	[/^(vce|vcn)/, 'technical/video-vcn.html']
];

export function docUrlForFamily(family: string): string {
	return DOCS + (FAMILY_PAGES.find(([prefix]) => prefix.test(family))?.[1] ?? PRESETS_TUNES);
}
