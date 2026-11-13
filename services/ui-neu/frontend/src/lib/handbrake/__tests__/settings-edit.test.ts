import { describe, it, expect } from 'vitest';
import type { HandbrakeSchemaSlimView, HandbrakeSettings } from '$lib/types/api.gen';
import fixture from './fixtures/slim-schema.json';
import {
	pruneUnreachable,
	resetBlock,
	resetCommon,
	setBlock,
	setCommon,
	storedCount,
	toPayload
} from '../settings-edit';

const schema = fixture as unknown as HandbrakeSchemaSlimView;

describe('common edits', () => {
	it('sets a key without mutating the input', () => {
		const before: HandbrakeSettings = { common: { A: 1 }, encoders: {} };
		const after = setCommon(before, 'B', 2);
		expect(after.common).toEqual({ A: 1, B: 2 });
		expect(before.common).toEqual({ A: 1 });
	});

	it('Reset removes the key', () => {
		const after = resetCommon({ common: { A: 1, B: 2 }, encoders: {} }, 'A');
		expect(after.common).toEqual({ B: 2 });
	});

	it('treats missing sections as empty', () => {
		expect(setCommon({}, 'A', 1)).toEqual({ common: { A: 1 }, encoders: {} });
		expect(resetCommon({}, 'A')).toEqual({ common: {}, encoders: {} });
	});
});

describe('block edits', () => {
	it('sets a key in a new and an existing block', () => {
		const one = setBlock({}, 'x264', 'VideoPreset', 'slow');
		const two = setBlock(one, 'x264', 'VideoTune', 'film');
		expect(two.encoders).toEqual({ x264: { VideoPreset: 'slow', VideoTune: 'film' } });
		expect(one.encoders).toEqual({ x264: { VideoPreset: 'slow' } });
	});

	it('Reset removes the key and keeps a non-empty block', () => {
		const s = { common: {}, encoders: { x264: { A: 1, B: 2 } } };
		expect(resetBlock(s, 'x264', 'A').encoders).toEqual({ x264: { B: 2 } });
	});

	it('Reset drops the block when it becomes empty', () => {
		const s = { common: {}, encoders: { x264: { A: 1 }, x265: { B: 2 } } };
		expect(resetBlock(s, 'x264', 'A').encoders).toEqual({ x265: { B: 2 } });
	});

	it('Reset of an absent block is a no-op', () => {
		expect(resetBlock({}, 'x264', 'A')).toEqual({ common: {}, encoders: {} });
	});
});

describe('pruneUnreachable', () => {
	it('drops blocks of encoders that cannot be reached', () => {
		const s = { common: { A: 1 }, encoders: { x265: { A: 1 }, x264: { A: 2 } } };
		const out = pruneUnreachable(s, ['nvenc_h264', 'qsv_h264', 'x264']);
		expect(out).toEqual({ common: { A: 1 }, encoders: { x264: { A: 2 } } });
		expect(Object.keys(s.encoders)).toEqual(['x265', 'x264']);
	});

	it('copes with missing sections', () => {
		expect(pruneUnreachable({}, ['x264'])).toEqual({ common: {}, encoders: {} });
	});
});

describe('toPayload', () => {
	it('is null for empty settings', () => {
		expect(toPayload({ common: {}, encoders: {} })).toBeNull();
		expect(toPayload({})).toBeNull();
		expect(toPayload({ common: {}, encoders: { x264: {} } })).toBeNull();
	});

	it('keeps common values and drops empty blocks', () => {
		expect(toPayload({ common: { A: 1 }, encoders: { x264: {}, x265: { B: 2 } } })).toEqual({
			common: { A: 1 },
			encoders: { x265: { B: 2 } }
		});
	});

	it('keeps a settings value that only has an encoder block', () => {
		expect(toPayload({ common: {}, encoders: { x264: { B: 2 } } })).toEqual({
			common: {},
			encoders: { x264: { B: 2 } }
		});
	});
});

describe('storedCount', () => {
	const s = {
		common: { PictureWidth: 1280, ChapterMarkers: true, VideoEncoder: 'x264', Unknown: 1 },
		encoders: { x264: { VideoPreset: 'slow', bit_depth: 10 }, x265: { VideoPreset: 'fast' } }
	};

	it('counts common keys of the tab', () => {
		expect(storedCount(s, 'dimensions', schema)).toBe(1);
		expect(storedCount(s, 'chapters', schema)).toBe(1);
		expect(storedCount(s, 'audio', schema)).toBe(0);
	});

	it('adds every encoder block key to the video tab', () => {
		expect(storedCount(s, 'video', schema)).toBe(1 + 3);
	});

	it('is zero for empty settings', () => {
		expect(storedCount({}, 'video', schema)).toBe(0);
	});
});
