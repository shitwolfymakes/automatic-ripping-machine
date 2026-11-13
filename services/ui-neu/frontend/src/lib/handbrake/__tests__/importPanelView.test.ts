import { describe, it, expect } from 'vitest';
import type { HandbrakeSchemaSlimView, ImportedPresetView } from '$lib/types/api.gen';
import { importPanelView, presetPickView } from '../import-panel-view';

const schema = { handbrake_tag: '1.9.0' } as HandbrakeSchemaSlimView;

function preset(over: Partial<ImportedPresetView> = {}): ImportedPresetView {
	return { path: ['Plex'], name: 'Good', importable: true, reason: null, ...over } as ImportedPresetView;
}

function view(over: Partial<Parameters<typeof importPanelView>[0]> = {}) {
	return importPanelView({ presets: null, schema, text: 'x', loading: false, ...over });
}

describe('importPanelView step 1', () => {
	it('is step 1 with the version line and Import enabled', () => {
		expect(view()).toMatchObject({
			step: 1,
			showVersionLine: true,
			versionTag: '1.9.0',
			canRead: true,
			readLabel: 'Import',
			showPicks: false,
			showSingleReason: false,
			singleReason: ''
		});
	});

	it('leaves out the version line with no schema', () => {
		expect(view({ schema: null })).toMatchObject({ showVersionLine: false, versionTag: '' });
	});

	it('cannot read blank text', () => {
		expect(view({ text: '  \n' }).canRead).toBe(false);
	});

	it('cannot read while loading, and says so', () => {
		expect(view({ loading: true })).toMatchObject({ canRead: false, readLabel: 'Importing...' });
	});
});

describe('importPanelView step 2', () => {
	it('shows the pick list for several presets', () => {
		expect(view({ presets: [preset(), preset()] })).toMatchObject({
			step: 2,
			showPicks: true,
			showSingleReason: false
		});
	});

	it('shows the reason of a single unimportable preset', () => {
		expect(view({ presets: [preset({ importable: false, reason: 'No encoder' })] })).toMatchObject({
			showPicks: false,
			showSingleReason: true,
			singleReason: 'No encoder'
		});
	});

	it('shows an empty reason when the unimportable preset has none', () => {
		expect(view({ presets: [preset({ importable: false, reason: undefined })] })).toMatchObject({
			showSingleReason: true,
			singleReason: ''
		});
	});

	it('shows nothing extra for a single importable preset', () => {
		expect(view({ presets: [preset()] })).toMatchObject({ showPicks: false, showSingleReason: false });
	});

	it('shows nothing extra for an empty list', () => {
		expect(view({ presets: [] })).toMatchObject({ step: 2, showPicks: false, showSingleReason: false });
	});
});

describe('importPanelView picks', () => {
	it('is empty on step 1', () => {
		expect(view().picks).toEqual([]);
	});

	it('has one pick per preset on step 2', () => {
		expect(view({ presets: [preset(), preset({ name: 'B', importable: false })] }).picks.map((p) => p.label)).toEqual([
			'Plex / Good',
			'Plex / B'
		]);
	});
});

describe('presetPickView', () => {
	it('joins the path and name, and enables an importable preset', () => {
		expect(presetPickView(preset({ path: ['Plex', 'Movies'] }))).toEqual({
			label: 'Plex / Movies / Good',
			disabled: false,
			reason: null
		});
	});

	it('disables an unimportable preset and shows its reason', () => {
		expect(presetPickView(preset({ importable: false, reason: 'No encoder' }))).toMatchObject({
			disabled: true,
			reason: 'No encoder'
		});
	});

	it('disables an unimportable preset with no reason', () => {
		expect(presetPickView(preset({ importable: false, reason: null }))).toMatchObject({
			disabled: true,
			reason: null
		});
	});

	it('hides a reason on an importable preset', () => {
		expect(presetPickView(preset({ reason: 'ignored' })).reason).toBeNull();
	});
});
