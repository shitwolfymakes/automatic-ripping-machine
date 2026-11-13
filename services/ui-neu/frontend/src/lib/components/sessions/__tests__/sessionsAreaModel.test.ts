import { describe, it, expect } from 'vitest';
import type { RipPresetView, SessionView, TranscodePresetView } from '$lib/types/api.gen';
import {
	activePresetKey,
	activeSessionKey,
	deletePresetMessage,
	deleteSessionMessage,
	isCreatingRipPreset,
	isCreatingTranscodePreset,
	isRipSidebarReadOnly,
	isSidebarStacked,
	shouldCloseBuilderAfterDelete,
	shouldClosePresetEditorsAfterDelete,
	transcodeSidebarMode,
	viewTabs,
	passthroughSessions,
	passthroughTranscodePresets,
	type EditorState
} from '../sessionsAreaModel';

const closed: EditorState = { builderOpen: false, sessionId: null, ripPresetId: null, transcodePresetId: null };
const asRip = (o: Partial<RipPresetView>) => o as RipPresetView;
const asTc = (o: Partial<TranscodePresetView>) => o as TranscodePresetView;
const asSession = (o: Partial<SessionView>) => o as SessionView;

describe('viewTabs', () => {
	it('lists the four tabs in order with counts, none for routing', () => {
		expect(viewTabs({ sessions: 3, rip: 0, transcode: 2 })).toEqual([
			{ key: 'sessions', label: 'Sessions', count: 3 },
			{ key: 'rip', label: 'Rip presets', count: 0 },
			{ key: 'transcode', label: 'Transcode presets', count: 2 },
			{ key: 'routing', label: 'Routing', count: undefined }
		]);
	});
});

describe('active keys', () => {
	it('activeSessionKey is the edited session only while the builder is open', () => {
		expect(activeSessionKey({ ...closed, builderOpen: true, sessionId: 's1' })).toBe('s1');
		expect(activeSessionKey({ ...closed, builderOpen: true })).toBeNull();
		expect(activeSessionKey({ ...closed, sessionId: 's1' })).toBeNull();
	});
	it('activePresetKey prefers the transcode editor, then rip, then none', () => {
		expect(activePresetKey({ ...closed, transcodePresetId: 't1', ripPresetId: 'r1' })).toBe('t1');
		expect(activePresetKey({ ...closed, ripPresetId: 'r1' })).toBe('r1');
		expect(activePresetKey(closed)).toBeNull();
	});
	it('isSidebarStacked follows the builder', () => {
		expect(isSidebarStacked({ ...closed, builderOpen: true })).toBe(true);
		expect(isSidebarStacked(closed)).toBe(false);
	});
});

describe('close after delete', () => {
	const open: EditorState = { builderOpen: true, sessionId: 's1', ripPresetId: 'r1', transcodePresetId: null };
	it('closes the builder only on a successful delete of the open session', () => {
		expect(shouldCloseBuilderAfterDelete('s1', true, open)).toBe(true);
	});
	it('keeps the builder open when the delete failed', () => {
		expect(shouldCloseBuilderAfterDelete('s1', false, open)).toBe(false);
	});
	it('keeps the builder open when another session was deleted or none is open', () => {
		expect(shouldCloseBuilderAfterDelete('s2', true, open)).toBe(false);
		expect(shouldCloseBuilderAfterDelete('s1', true, { ...open, builderOpen: false })).toBe(false);
	});
	it('closes the preset editors only on a successful delete of the open preset, even when stacked', () => {
		expect(shouldClosePresetEditorsAfterDelete('r1', true, open)).toBe(true);
		expect(shouldClosePresetEditorsAfterDelete('r1', false, open)).toBe(false);
		expect(shouldClosePresetEditorsAfterDelete('r2', true, open)).toBe(false);
		expect(shouldClosePresetEditorsAfterDelete('r1', true, closed)).toBe(false);
	});
});

describe('sidebar decisions', () => {
	it('transcodeSidebarMode views built-ins and edits the rest', () => {
		expect(transcodeSidebarMode(asTc({ is_builtin: true }))).toBe('view');
		expect(transcodeSidebarMode(asTc({ is_builtin: false }))).toBe('edit');
	});
	it('isRipSidebarReadOnly is true only for a built-in preset', () => {
		expect(isRipSidebarReadOnly(asRip({ is_builtin: true }))).toBe(true);
		expect(isRipSidebarReadOnly(asRip({ is_builtin: false }))).toBe(false);
		expect(isRipSidebarReadOnly(null)).toBe(false);
	});
	it('isCreatingRipPreset is true only for an open sidebar with no preset', () => {
		expect(isCreatingRipPreset({ preset: null })).toBe(true);
		expect(isCreatingRipPreset({ preset: asRip({ id: 'r1' }) })).toBe(false);
		expect(isCreatingRipPreset(null)).toBe(false);
	});
	it('isCreatingTranscodePreset is true only for an open sidebar in new mode', () => {
		expect(isCreatingTranscodePreset({ mode: 'new' })).toBe(true);
		expect(isCreatingTranscodePreset({ mode: 'edit' })).toBe(false);
		expect(isCreatingTranscodePreset(null)).toBe(false);
	});
});

describe('messages', () => {
	it('builds the delete confirmations, empty without a target', () => {
		expect(deleteSessionMessage({ name: 'Movies' })).toBe('Delete the session "Movies"? This cannot be undone.');
		expect(deleteSessionMessage(null)).toBe('');
		expect(deletePresetMessage({ name: 'HQ' })).toBe('Delete the preset "HQ"? This cannot be undone.');
		expect(deletePresetMessage(null)).toBe('');
	});
});

describe('passthrough filtering', () => {
	const presets = [asTc({ id: 'p-none', tool: 'none' }), asTc({ id: 'p-hb', tool: 'handbrake' })];
	const sessions = [
		asSession({ id: 'a', transcode_preset_id: null, media_type: 'movie' }),
		asSession({ id: 'b', transcode_preset_id: 'p-none', media_type: 'movie' }),
		asSession({ id: 'c', transcode_preset_id: 'p-hb', media_type: 'movie' })
	];
	it('keeps only passthrough sessions', () => {
		expect(passthroughSessions(sessions, presets).map((s) => s.id)).toEqual(['a', 'b']);
	});
	it('keeps only passthrough presets', () => {
		expect(passthroughTranscodePresets(presets)).toEqual([presets[0]]);
	});
});
