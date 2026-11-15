import { describe, it, expect } from 'vitest';
import { docUrlFor, docUrlForFamily, OFFICIAL_PRESETS_URL } from '../doc-links';

const BASE = 'https://handbrake.fr/docs/en/latest/';

describe('docUrlFor', () => {
	it.each([
		['dimensions', 'Size', 'advanced/resizing-video.html'],
		['dimensions', 'Orientation', 'advanced/resizing-video.html'],
		['dimensions', 'Cropping', 'advanced/resizing-video.html'],
		['dimensions', 'Padding', 'advanced/resizing-video.html'],
		['dimensions', 'Pixel aspect', 'technical/anamorphic-guide.html'],
		['filters', 'Denoise', 'technical/filters-summary.html'],
		['filters', 'General', 'technical/filters-summary.html'],
		['video', 'Rate control', 'technical/video-cq-vs-abr.html'],
		['video', 'Framerate', 'technical/frame-rates.html'],
		['video', 'Color', 'technical/hdr.html'],
		['video', 'Encoder', 'technical/video-presets-tunes.html'],
		['video', 'Other', 'technical/video-codecs.html'],
		['audio', 'Tracks', 'advanced/audio-subtitle-defaults.html'],
		['subtitles', 'Burn in', 'advanced/audio-subtitle-defaults.html'],
		['chapters', 'Chapters', 'advanced/chapter-markers.html'],
		['summary', 'Container', 'advanced/metadata-passthru.html'],
		['dimensions', 'Unknown group', 'cli/command-line-reference.html'],
		['video', 'Unknown group', 'cli/command-line-reference.html']
	] as const)('%s / %s -> %s', (tab, group, page) => {
		expect(docUrlFor(tab, group)).toBe(BASE + page);
	});
});

describe('OFFICIAL_PRESETS_URL', () => {
	it("is HandBrake's official presets page", () => {
		expect(OFFICIAL_PRESETS_URL).toBe(BASE + 'technical/official-presets.html');
	});
});

describe('docUrlForFamily', () => {
	it.each([
		['nvenc_h264', 'technical/video-nvenc.html'],
		['qsv_av1', 'technical/video-qsv.html'],
		['vce_h265', 'technical/video-vcn.html'],
		['vcn_h264', 'technical/video-vcn.html'],
		['x264', 'technical/video-presets-tunes.html'],
		['svt_av1', 'technical/video-presets-tunes.html'],
		['mf_h264', 'technical/video-presets-tunes.html']
	])('%s -> %s', (family, page) => {
		expect(docUrlForFamily(family)).toBe(BASE + page);
	});
});
