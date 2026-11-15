import { describe, it, expect } from 'vitest';
import type { EncoderAvailabilityView } from '$lib/types/api.gen';
import {
	HARDWARE_HINT,
	presetBlockView,
	presetSidebarView,
	settingsPanelView,
	type PresetBlockInput,
	type PresetSidebarInput
} from '../panelView';
import { initialDraft, type Draft } from '../sidebarModel';

const draft = (over: Partial<Draft> = {}): Draft => ({ ...initialDraft(null), name: 'Movies', ...over });
const avail = (over: Partial<EncoderAvailabilityView>): EncoderAvailabilityView =>
	({ id: 'any_h264', label: 'H.264 (any)', vendor: 'cpu', available: true, ...over }) as EncoderAvailabilityView;

describe('settingsPanelView', () => {
	const base = { tab: 'summary' as const, encoder: 'preset', availability: [] };

	it('uses the video section on the video tab only', () => {
		expect(settingsPanelView({ ...base, tab: 'video' }).section).toBe('video');
		expect(settingsPanelView({ ...base, tab: 'audio' }).section).toBe('plain');
	});

	it('labels the encoder from availability, with a generic fallback', () => {
		const list = [avail({})];
		expect(settingsPanelView({ ...base, encoder: 'any_h264', availability: list }).encoderLabel).toBe('H.264 (any)');
		expect(settingsPanelView({ ...base, encoder: 'gone', availability: list }).encoderLabel).toBe('This preset');
	});

	it('shows the AMD note for an any-vendor encoder when a VAAPI encoder is available', () => {
		const list = [avail({ id: 'vaapi_h264', vendor: 'vaapi' })];
		expect(settingsPanelView({ ...base, encoder: 'any_h264', availability: list }).showAmdNote).toBe(true);
		expect(settingsPanelView({ ...base, encoder: 'any_h264', availability: [avail({})] }).showAmdNote).toBe(false);
		expect(settingsPanelView({ ...base, encoder: 'preset', availability: list }).showAmdNote).toBe(false);
	});
});

describe('presetBlockView', () => {
	const input = (over: Partial<PresetBlockInput> = {}): PresetBlockInput => ({
		draft: draft(),
		readonly: false,
		builtinNames: ['Fast 1080p30'],
		encodersLoading: false,
		encoderCount: 3,
		presetEncoderId: 'preset',
		...over
	});

	it('disables the encoder when read-only, locked or loading', () => {
		expect(presetBlockView(input()).encoderDisabled).toBe(false);
		expect(presetBlockView(input({ readonly: true })).encoderDisabled).toBe(true);
		expect(presetBlockView(input({ draft: draft({ tool: 'none' }) })).encoderDisabled).toBe(true);
		expect(presetBlockView(input({ encodersLoading: true })).encoderDisabled).toBe(true);
	});

	it('lists encoders as loading, empty or grouped', () => {
		expect(presetBlockView(input({ encodersLoading: true })).encoderList).toBe('loading');
		expect(presetBlockView(input({ encoderCount: 0 })).encoderList).toBe('empty');
		expect(presetBlockView(input()).encoderList).toBe('groups');
	});

	it('hints only when the preset encoder is kept with a hardware-named preset', () => {
		const named = (preset_ref: string | null, encoder = 'preset') => draft({ preset_ref, encoder });
		expect(presetBlockView(input({ draft: named('H.265 NVENC 1080p') })).encoderHint).toBe(HARDWARE_HINT);
		expect(presetBlockView(input({ draft: named('Fast 1080p30') })).encoderHint).toBeNull();
		expect(presetBlockView(input({ draft: named(null) })).encoderHint).toBeNull();
		expect(presetBlockView(input({ draft: named('H.265 NVENC 1080p', 'any_h265') })).encoderHint).toBeNull();
	});

	it('lists base presets only for HandBrake with a loaded schema', () => {
		expect(presetBlockView(input()).baseNames).toEqual(['Fast 1080p30']);
		expect(presetBlockView(input({ builtinNames: null })).baseNames).toBeNull();
		expect(presetBlockView(input({ draft: draft({ tool: 'abcde' }) })).baseNames).toBeNull();
	});

	it('reads a VAAPI encoder as ffmpeg: its own label, no tabs, cleared settings noted', () => {
		const vaapi = draft({ encoder: 'vaapi_h264', settings: { common: { A: 1 }, encoders: {} } });
		const view = presetBlockView(input({ draft: vaapi }));
		expect(view).toMatchObject({
			usesFfmpegVaapi: true,
			extraArgsLabel: 'ffmpeg arguments',
			showOverrideHelp: false,
			showClearedNote: true
		});
		const plain = presetBlockView(input());
		expect(plain).toMatchObject({
			usesFfmpegVaapi: false,
			extraArgsLabel: 'Extra args',
			showOverrideHelp: true,
			showClearedNote: false
		});
	});
});

describe('presetSidebarView', () => {
	const input = (over: Partial<PresetSidebarInput> = {}): PresetSidebarInput => ({
		mode: 'edit',
		importing: false,
		draft: draft(),
		submitting: false,
		cloneAvailable: true,
		failure: null,
		unplacedCount: 0,
		...over
	});

	it('is read-only only in view mode', () => {
		expect(presetSidebarView(input({ mode: 'view' })).readonly).toBe(true);
		expect(presetSidebarView(input({ mode: 'edit' })).readonly).toBe(false);
		expect(presetSidebarView(input({ mode: 'new' })).readonly).toBe(false);
	});

	it('swaps the form and footer for the import panel while importing', () => {
		expect(presetSidebarView(input({ importing: true }))).toMatchObject({
			showImport: true,
			showFooter: false,
			importDisabled: true
		});
		expect(presetSidebarView(input())).toMatchObject({ showImport: false, showFooter: true, importDisabled: false });
	});

	it('disables import on a read-only preset', () => {
		expect(presetSidebarView(input({ mode: 'view' })).importDisabled).toBe(true);
	});

	it('offers Clone only on a read-only preset it can clone', () => {
		expect(presetSidebarView(input({ mode: 'view' })).showClone).toBe(true);
		expect(presetSidebarView(input({ mode: 'view', cloneAvailable: false })).showClone).toBe(false);
		expect(presetSidebarView(input({ mode: 'edit' })).showClone).toBe(false);
	});

	it('shows the failure banner, with Retry only when the schema is missing', () => {
		const failure = (schemaMissing: boolean) => ({ issues: null, message: 'No', schemaMissing });
		expect(presetSidebarView(input())).toMatchObject({ failure: null, showRetry: false });
		expect(presetSidebarView(input({ failure: failure(false) }))).toMatchObject({
			failure: failure(false),
			showRetry: false
		});
		expect(presetSidebarView(input({ failure: failure(true) })).showRetry).toBe(true);
	});

	it('lists unplaced issues only when there are some', () => {
		expect(presetSidebarView(input()).showUnplaced).toBe(false);
		expect(presetSidebarView(input({ unplacedCount: 2 })).showUnplaced).toBe(true);
	});

	it('shows the settings area for tabs, a note for a VAAPI encoder, nothing for other tools', () => {
		expect(presetSidebarView(input()).settings).toBe('tabs');
		expect(presetSidebarView(input({ draft: draft({ encoder: 'vaapi_h264' }) })).settings).toBe('vaapi-note');
		expect(presetSidebarView(input({ draft: draft({ tool: 'abcde' }) })).settings).toBe('none');
	});

	it('submits only an editable, named, idle draft', () => {
		expect(presetSidebarView(input()).canSubmit).toBe(true);
		expect(presetSidebarView(input({ mode: 'view' })).canSubmit).toBe(false);
		expect(presetSidebarView(input({ submitting: true })).canSubmit).toBe(false);
		expect(presetSidebarView(input({ draft: draft({ name: '  ' }) })).canSubmit).toBe(false);
	});
});
