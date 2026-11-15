import { describe, it, expect } from 'vitest';
import registry from '../field-docs.json';
import { docsHref, docsLinkFor, familyDocs, handbrakeKeyDocs, headingAnchor, helpHref } from '../field-docs';

const BASE = 'https://handbrake.fr/docs/en/latest/';
const FIELDS = registry.fields as Record<string, Record<string, unknown>>;

function external(page: string) {
	return { type: 'external', url: BASE + page };
}

describe('docsLinkFor', () => {
	it('returns an external entry', () => {
		expect(docsLinkFor('handbrake.group.dimensions.Size')).toEqual(external('advanced/resizing-video.html'));
	});

	it('returns an internal entry', () => {
		expect(docsLinkFor('config.auto_rip_on_insert')).toEqual({
			type: 'internal',
			page: 'guide/configuring-arm',
			section: 'Rip / transcode behaviour'
		});
	});

	it('returns null for an opt-out, even when a fallback has a link', () => {
		const optOut = Object.keys(FIELDS).find((id) => 'none' in FIELDS[id]);
		expect(optOut).toBeDefined();
		expect(docsLinkFor(optOut as string)).toBeNull();
		expect(docsLinkFor(optOut as string, 'handbrake.group.dimensions.Size')).toBeNull();
	});

	it('returns null for an unknown id, or one whose fallback is unknown or an opt-out', () => {
		expect(docsLinkFor('config.NOT_A_FIELD')).toBeNull();
		expect(docsLinkFor('config.NOT_A_FIELD', 'config.ALSO_NOT')).toBeNull();
		const optOut = Object.keys(FIELDS).find((id) => 'none' in FIELDS[id]) as string;
		expect(docsLinkFor('config.NOT_A_FIELD', optOut)).toBeNull();
	});

	it('prefers the id over its fallback', () => {
		expect(docsLinkFor('handbrake.family.nvenc', 'handbrake.group.dimensions.Size')).toEqual(
			external('technical/video-nvenc.html')
		);
	});

	it('uses the fallback entry when the id has none', () => {
		expect(docsLinkFor('config.NOT_A_FIELD', 'handbrake.group.dimensions.Size')).toEqual(
			external('advanced/resizing-video.html')
		);
	});
});

describe('handbrakeKeyDocs', () => {
	it.each([
		['dimensions', 'Size', 'advanced/resizing-video.html'],
		['dimensions', 'Orientation', 'advanced/resizing-video.html'],
		['dimensions', 'Cropping', 'advanced/resizing-video.html'],
		['dimensions', 'Padding', 'advanced/resizing-video.html'],
		['dimensions', 'Pixel aspect', 'technical/anamorphic-guide.html'],
		['filters', 'Denoise', 'technical/filters-summary.html'],
		['video', 'Rate control', 'technical/video-cq-vs-abr.html'],
		['video', 'Framerate', 'technical/frame-rates.html'],
		['video', 'Color', 'technical/hdr.html'],
		['video', 'Encoder', 'technical/video-presets-tunes.html'],
		['audio', 'Tracks', 'advanced/audio-subtitle-defaults.html'],
		['subtitles', 'Burn in', 'advanced/audio-subtitle-defaults.html'],
		['chapters', 'Chapters', 'advanced/chapter-markers.html'],
		['summary', 'Container', 'advanced/metadata-passthru.html']
	])('%s / %s resolves to its group page', (tab, group, page) => {
		expect(handbrakeKeyDocs(tab, group, 'NoOverrideKey')).toEqual(external(page));
	});

	it('returns null for a group the registry does not know', () => {
		expect(handbrakeKeyDocs('video', 'Unknown group', 'NoOverrideKey')).toBeNull();
	});
});

describe('familyDocs', () => {
	it.each([
		['nvenc_h264', 'technical/video-nvenc.html'],
		['qsv_av1', 'technical/video-qsv.html'],
		['vce_h265', 'technical/video-vcn.html'],
		['vcn_h264', 'technical/video-vcn.html'],
		['x264', 'technical/video-presets-tunes.html'],
		['svt_av1', 'technical/video-presets-tunes.html'],
		['mf_h264', 'technical/video-presets-tunes.html']
	])('%s -> %s', (family, page) => {
		expect(familyDocs(family)).toEqual(external(page));
	});

	it('maps onto exactly the family ids the registry declares', () => {
		const declared = Object.keys(FIELDS)
			.filter((id) => id.startsWith('handbrake.family.'))
			.map((id) => id.slice('handbrake.family.'.length))
			.sort();
		expect(declared).toEqual(['default', 'nvenc', 'qsv', 'vcn']);
		const probes = ['nvenc_h264', 'qsv_av1', 'vcn_h264', 'x264'];
		const resolved = probes.map((p) => familyDocs(p));
		for (const [i, name] of ['nvenc', 'qsv', 'vcn', 'default'].entries()) {
			expect(resolved[i]).toEqual(docsLinkFor(`handbrake.family.${name}`));
		}
	});
});

describe('official presets entry', () => {
	it("is HandBrake's official presets page", () => {
		expect(docsLinkFor('form.transcode_preset.preset_ref')).toEqual(external('technical/official-presets.html'));
	});
});

// Anchors confirmed against the docs site's slugger (github-slugger, site/package.json).
describe('headingAnchor', () => {
	it.each([
		['Rip / transcode behaviour', 'rip--transcode-behaviour'],
		['3. Drives', '3-drives'],
		['How the key works', 'how-the-key-works'],
		['Enabling GPU transcoding', 'enabling-gpu-transcoding'],
		["What's new? (v3)", 'whats-new-v3'],
		['Über cool_thing – x', 'über-cool_thing--x'],
		['A  B', 'a--b']
	])('%s -> %s', (text, anchor) => {
		expect(headingAnchor(text)).toBe(anchor);
	});
});

describe('helpHref and docsHref', () => {
	it('builds a help route with the section anchor', () => {
		expect(helpHref({ type: 'internal', page: 'guide/configuring-arm', section: 'Rip / transcode behaviour' })).toBe(
			'/help/guide/configuring-arm#rip--transcode-behaviour'
		);
	});

	it('omits the anchor when there is no section', () => {
		expect(helpHref({ type: 'internal', page: 'guide/configuring-arm' })).toBe('/help/guide/configuring-arm');
	});

	it('opens an external link at its url and an internal one at its help route', () => {
		expect(docsHref({ type: 'external', url: 'https://example.test/x' })).toBe('https://example.test/x');
		expect(docsHref({ type: 'internal', page: 'guide/home' })).toBe('/help/guide/home');
	});

	it('has no href for no link', () => {
		expect(docsHref(null)).toBeUndefined();
	});
});

describe('committed copy', () => {
	it('is byte-identical to the registry in arm_common (devtools/regen-field-docs.sh)', async () => {
		const { readFileSync } = await import('node:fs');
		// vitest runs from services/ui-neu/frontend.
		const copy = readFileSync('src/lib/docs/field-docs.json');
		const source = readFileSync('../../../packages/arm_common/arm_common/field_docs.json');
		expect(copy.equals(source)).toBe(true);
	});
});
