import { describe, it, expect } from 'vitest';
import type { EncoderAvailabilityView, HandbrakeSchemaSlimView, ImportedPresetView } from '$lib/types/api.gen';
import slim from './fixtures/slim-schema.json';
import tenBit from './fixtures/x265-10bit-import-response.json';
import plex from './fixtures/plex-import-response.json';
import { applyProposal, defaultPick, familyLabel, reviewRows } from '../import-review';
import { initialDraft } from '../draft';

const schema = slim as unknown as HandbrakeSchemaSlimView;
const response = plex as unknown as { presets: ImportedPresetView[] };
const PLEX = response.presets[0];
const TEN = (tenBit as unknown as { presets: ImportedPresetView[] }).presets[0];

function enc(id: string, label: string): EncoderAvailabilityView {
	return {
		id,
		label,
		group: 'any',
		engine: 'handbrake',
		kind: 'any',
		vendor: null,
		codec: null,
		available: true,
		reason: null
	};
}
const AVAILABILITY = [
	enc('any_h264', 'Any H.264'),
	enc('x264', 'CPU x264'),
	enc('qsv_h264', 'Intel QSV H.264'),
	enc('nvenc_h264', 'NVIDIA H.264'),
	enc('x265', 'CPU x265'),
	enc('nvenc_h265', 'NVIDIA H.265'),
	enc('qsv_h265', 'Intel QSV H.265')
];

function entry(over: Partial<ImportedPresetView>): ImportedPresetView {
	return { ...PLEX, ...over };
}

describe('familyLabel', () => {
	it('prefers the availability label and falls back to the family id', () => {
		expect(familyLabel('x264', AVAILABILITY)).toBe('CPU x264');
		expect(familyLabel('svt_av1', AVAILABILITY)).toBe('svt_av1');
	});
});

describe('reviewRows on the Plex export', () => {
	const review = reviewRows(PLEX, schema, AVAILABILITY);

	it('names the encoders, codec, depth and container', () => {
		expect(review.encoderInFile).toBe('NVIDIA H.264');
		expect(review.codecDepth).toBe('H.264, 8-bit');
		expect(review.encoderInArm).toBe('Any H.264');
		expect(review.container).toBe('mkv');
		expect(review.storedFor).toBe('NVIDIA H.264');
	});

	it('lists the source block values with schema labels', () => {
		expect(review.values).toEqual([
			['Bit depth', '8'],
			['Encoder preset', 'slower'],
			['Encoder profile', 'main'],
			['Encoder level', '4.0'],
			['Constant quality', '18']
		]);
	});

	it('reports where the depth was copied', () => {
		expect(review.copiedTo).toEqual(['Intel QSV H.264', 'CPU x264']);
		expect(review.copiedLine).toBe('Bit depth 8 also set for Intel QSV H.264, CPU x264');
	});

	it('counts stored settings per tab and in total', () => {
		expect(review.tabCounts.video).toBeGreaterThan(0);
		expect(review.total).toBe(Object.values(review.tabCounts).reduce((a, b) => a + b, 0));
	});

	it('writes the one-line notes', () => {
		expect(review.notes).toEqual([
			'Only bit depth is copied. Other encoders keep their defaults.',
			'Not used by NVIDIA H.264, not imported: VideoMultiPass, VideoTurboMultiPass, x264UseAdvancedOptions',
			'1 key dropped (not in HandBrake 1.11.1): VideoColorMatrixCode'
		]);
	});
});

describe('reviewRows on a 10-bit export', () => {
	const review = reviewRows(TEN, schema, AVAILABILITY);

	it('resolves the variant to its family', () => {
		expect(review.encoderInFile).toBe('CPU x265');
		expect(review.storedFor).toBe('CPU x265');
		expect(review.codecDepth).toBe('H.265, 10-bit');
		expect(review.values[0]).toEqual(['Bit depth', '10']);
		expect(review.values).toHaveLength(7);
	});

	it('copies the real depth and never shows the variant name', () => {
		expect(review.copiedLine).toBe('Bit depth 10 also set for NVIDIA H.265, Intel QSV H.265');
		expect(review.notes.join(' ')).not.toContain('x265_10bit');
		expect(review.notes.join(' ')).not.toContain('undefined');
	});

	it('takes the depth from the suffix when the block has none, else 8', () => {
		const bare = { ...TEN.proposal!, handbrake_settings: { common: {}, encoders: {} } };
		expect(reviewRows(entry({ source_encoder: 'x265_10bit', proposal: bare }), schema).codecDepth).toBe(
			'H.265, 10-bit'
		);
		expect(reviewRows(entry({ source_encoder: 'x265', proposal: bare }), schema).codecDepth).toBe('H.265, 8-bit');
	});

	it('lists eight-bit-only families', () => {
		const r = reviewRows(entry({ ...TEN, eight_bit_only: ['x265'] }), schema, AVAILABILITY);
		expect(r.eightBitOnly).toEqual(['CPU x265: 8-bit on this encoder']);
	});
});

describe('reviewRows edge cases', () => {
	it('pluralises dropped keys and appends warnings and issue messages', () => {
		const r = reviewRows(
			entry({
				dropped_keys: ['A', 'B'],
				not_imported: [],
				copied_depth_to: [],
				warnings: ['Exported from HandBrake 9.0.0'],
				issues: [{ key: 'X', message: 'X is out of range' } as never]
			}),
			schema,
			AVAILABILITY
		);
		expect(r.copiedLine).toBeNull();
		expect(r.notes).toEqual([
			'2 keys dropped (not in HandBrake 1.11.1): A, B',
			'Exported from HandBrake 9.0.0',
			'X is out of range'
		]);
	});

	it('lists eight-bit-only families', () => {
		const r = reviewRows(entry({ eight_bit_only: ['x264'], dropped_keys: [] }), schema, AVAILABILITY);
		expect(r.eightBitOnly).toEqual(['CPU x264: 8-bit on this encoder']);
	});

	it('leaves the codec out for an unknown family', () => {
		const proposal = { ...PLEX.proposal!, handbrake_settings: { common: {}, encoders: {} } };
		const r = reviewRows(entry({ source_encoder: 'mystery', proposal }), schema);
		expect(r.codecDepth).toBe('8-bit');
		expect(r.values).toEqual([]);
	});

	it('falls back to the key name when the schema has no label, and tolerates absent encoders', () => {
		const proposal = { ...PLEX.proposal!, handbrake_settings: { common: {}, encoders: { x264: { Odd: 1 } } } };
		expect(reviewRows(entry({ source_encoder: 'x264', proposal }), schema).values).toEqual([['Odd', '1']]);
		const none = { ...PLEX.proposal!, handbrake_settings: {} };
		expect(reviewRows(entry({ proposal: none }), schema).values).toEqual([]);
	});

	it('reviews an unimportable entry as blanks plus its messages', () => {
		const r = reviewRows(entry({ proposal: null, importable: false, warnings: ['w'] }), schema, AVAILABILITY);
		expect(r.total).toBe(0);
		expect(r.encoderInArm).toBe('');
		expect(r.notes).toEqual(['w']);
	});
});

describe('defaultPick', () => {
	it('picks the first importable entry, or none', () => {
		expect(defaultPick([entry({ importable: false }), PLEX])).toBe(1);
		expect(defaultPick([entry({ importable: false })])).toBeNull();
		expect(defaultPick([])).toBeNull();
	});
});

describe('applyProposal', () => {
	it('fills name, container, encoder and settings into an empty draft', () => {
		const d = applyProposal(initialDraft(null), PLEX);
		expect(d.name).toBe('Custom_Plex_720p');
		expect(d.encoder).toBe('any_h264');
		expect(d.settings).toBe(PLEX.proposal!.handbrake_settings);
	});

	it('clears the base preset', () => {
		const d = applyProposal({ ...initialDraft(null), preset_ref: 'Fast 1080p30' }, PLEX);
		expect(d.preset_ref).toBeNull();
	});

	it('keeps a name the draft already has', () => {
		const d = applyProposal({ ...initialDraft(null), name: 'Mine' }, PLEX);
		expect(d.name).toBe('Mine');
	});

	it('returns the draft unchanged for an unimportable entry', () => {
		const d = initialDraft(null);
		expect(applyProposal(d, entry({ proposal: null }))).toBe(d);
	});
});
