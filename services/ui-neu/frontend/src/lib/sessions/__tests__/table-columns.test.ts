import { describe, it, expect, vi } from 'vitest';

vi.mock('$lib/stores/encoders.svelte', () => ({
	encoderLabel: (id: string | null | undefined) =>
		id === 'any_h265' ? 'Any GPU H.265' : id === 'preset' ? '' : (id ?? '')
}));

import { deleteGuard, openLabel, ripPresetColumns, sessionColumns, transcodePresetColumns } from '../table-columns';

const rip = (over = {}) => ({
	id: 'r1',
	name: 'Movie: Main Feature',
	media_type: 'movie' as const,
	is_builtin: false,
	track_selection: 'main_feature' as const,
	identification_mode: 'required' as const,
	output_mode: 'tracks' as const,
	track_filters_json: null,
	created_by_user_id: null,
	created_at: null,
	updated_at: null,
	...over
});

const transcode = (over = {}) => ({
	id: 't1',
	name: 'H.265 MKV',
	media_type: 'movie' as const,
	is_builtin: false,
	tool: 'handbrake' as const,
	preset_ref: null,
	handbrake_settings: null,
	container: 'mkv' as const,
	encoder: 'any_h265',
	extra_args: null,
	created_by_user_id: null,
	created_at: null,
	updated_at: null,
	...over
});

const cells = <R>(cols: Array<{ id: string; cell: (r: R) => unknown }>, row: R) =>
	Object.fromEntries(cols.map((c) => [c.id, c.cell(row)]));

describe('ripPresetColumns', () => {
	it('lists the columns in order, with Used by end-aligned', () => {
		const cols = ripPresetColumns({});
		expect(cols.map((c) => c.header)).toEqual([
			'Preset',
			'Media',
			'Type',
			'Tracks',
			'Identification',
			'Output',
			'Track filters',
			'Used by'
		]);
		expect(cols.filter((c) => c.align === 'end').map((c) => c.header)).toEqual(['Used by']);
	});

	it('formats a custom preset without track filters', () => {
		const c = cells(ripPresetColumns({ r1: 2 }), rip());
		expect(c).toEqual({
			name: { text: 'Movie: Main Feature' },
			media: { text: 'Movie', pill: { tone: 'movie' } },
			type: { text: 'Custom', pill: { tone: 'custom' } },
			tracks: { text: 'Main feature' },
			identification: { text: 'Required', muted: false },
			output: { text: 'Tracks' },
			filters: { text: 'None', muted: true },
			usedBy: { text: '2', muted: false }
		});
	});

	it('formats a built-in preset that skips identification and is unused', () => {
		const c = cells(ripPresetColumns({}), rip({ is_builtin: true, identification_mode: 'skip' }));
		expect(c).toMatchObject({
			type: { text: 'Built-in', pill: { tone: 'builtin' } },
			identification: { text: 'Skipped', muted: true },
			usedBy: { text: '0', muted: true }
		});
	});

	it('counts track filters, singular and plural, and ignores an empty object', () => {
		const filters = (o: Record<string, unknown> | null) => ripPresetColumns({})[6].cell(rip({ track_filters_json: o }));
		expect(filters({ min_length_seconds: 1200 })).toEqual({ text: '1 filter' });
		expect(filters({ a: 1, b: 2 })).toEqual({ text: '2 filters' });
		expect(filters({})).toEqual({ text: 'None', muted: true });
	});

	it('shows an unknown identification mode as it is', () => {
		const cell = ripPresetColumns({})[4].cell(rip({ identification_mode: 'future_mode' }));
		expect(cell).toEqual({ text: 'future_mode', muted: false });
	});
});

describe('transcodePresetColumns', () => {
	it('lists the columns in order, with Settings and Used by end-aligned', () => {
		const cols = transcodePresetColumns({});
		expect(cols.map((c) => c.header)).toEqual([
			'Preset',
			'Media',
			'Type',
			'Tool',
			'Container',
			'Encoder',
			'Base preset',
			'Settings',
			'Used by'
		]);
		expect(cols.filter((c) => c.align === 'end').map((c) => c.header)).toEqual(['Settings', 'Used by']);
	});

	it('formats a HandBrake preset with a base preset and stored settings', () => {
		const settings = { common: { a: 1, b: 2 }, encoders: { x264: { c: 3 } } };
		const c = cells(
			transcodePresetColumns({ t1: 4 }),
			transcode({ preset_ref: 'Fast 1080p30', handbrake_settings: settings })
		);
		expect(c).toEqual({
			name: { text: 'H.265 MKV' },
			media: { text: 'Movie', pill: { tone: 'movie' } },
			type: { text: 'Custom', pill: { tone: 'custom' } },
			tool: { text: 'HandBrake' },
			container: { text: 'MKV' },
			encoder: { text: 'Any GPU H.265' },
			base: { text: 'Fast 1080p30' },
			settings: { text: '3', muted: false },
			usedBy: { text: '4', muted: false }
		});
	});

	it('shows no base preset and zero settings dimmed', () => {
		const c = cells(transcodePresetColumns({}), transcode());
		expect(c).toMatchObject({
			base: { text: 'None', muted: true },
			settings: { text: '0', muted: true },
			usedBy: { text: '0', muted: true }
		});
	});

	it('flags a preset with issues as Needs review', () => {
		const cell = transcodePresetColumns({})[0].cell(
			transcode({ issues: [{ key: 'k', code: 'unknown_key' as const, message: 'm' }] })
		);
		expect(cell).toEqual({ text: 'H.265 MKV', badges: [{ text: 'Needs review', tone: 'warn' }] });
	});

	it('notes that an encoder lands on the CPU on this host', () => {
		const cell = transcodePresetColumns({})[5].cell(transcode({ host_notes: ['encodes_on_cpu_here'] }));
		expect(cell).toEqual({ text: 'Any GPU H.265', sub: 'Encodes on CPU on this host' });
	});

	it('names the base preset default when the encoder is left to the base preset', () => {
		const cell = transcodePresetColumns({})[5].cell(transcode({ encoder: 'preset' }));
		expect(cell).toEqual({ text: 'Preset default' });
	});

	it('shows Not used for encoder, base preset and settings when the tool is not HandBrake', () => {
		const c = cells(transcodePresetColumns({}), transcode({ tool: 'none', preset_ref: 'ignored' }));
		expect(c).toMatchObject({
			tool: { text: 'None' },
			encoder: { text: 'Not used', muted: true },
			base: { text: 'Not used', muted: true },
			settings: { text: 'Not used', muted: true }
		});
	});
});

describe('Media and Type pills', () => {
	it('tone the media pill by media type, in both tables', () => {
		const tv = rip({ media_type: 'tv' });
		expect(ripPresetColumns({})[1].cell(tv)).toEqual({ text: 'TV', pill: { tone: 'tv' } });
		expect(transcodePresetColumns({})[1].cell(transcode({ media_type: 'music' }))).toEqual({
			text: 'Music',
			pill: { tone: 'music' }
		});
	});

	it('tag the Type column Custom or Built-in, in both tables', () => {
		expect(ripPresetColumns({})[2].cell(rip({ is_builtin: true })).pill).toEqual({ tone: 'builtin' });
		expect(ripPresetColumns({})[2].cell(rip()).pill).toEqual({ tone: 'custom' });
		expect(transcodePresetColumns({})[2].cell(transcode({ is_builtin: true })).pill).toEqual({ tone: 'builtin' });
		expect(transcodePresetColumns({})[2].cell(transcode()).pill).toEqual({ tone: 'custom' });
	});
});

describe('openLabel', () => {
	it('is Edit for a custom preset and View for a built-in', () => {
		expect(openLabel({ is_builtin: false })).toBe('Edit');
		expect(openLabel({ is_builtin: true })).toBe('View');
	});
});

describe('deleteGuard', () => {
	it('disables Delete for a built-in, even an unused one', () => {
		expect(deleteGuard({ is_builtin: true }, 0)).toEqual({
			disabled: true,
			title: 'Built-in preset: clone to edit or remove'
		});
	});

	it('disables Delete for a preset a session uses', () => {
		expect(deleteGuard({ is_builtin: false }, 2)).toEqual({
			disabled: true,
			title: 'Used by 2 session(s): repoint them first'
		});
	});

	it('leaves Delete on for an unused custom preset', () => {
		expect(deleteGuard({ is_builtin: false }, 0)).toEqual({ disabled: false });
	});
});

describe('sessionColumns', () => {
	const session = (over = {}) =>
		({
			id: 's1',
			name: 'Custom Plex 720p',
			media_type: 'movie',
			is_builtin: false,
			rip_preset_id: 'r1',
			transcode_preset_id: 't1',
			output_path_template: 'x/{title}.{ext}',
			overrides_json: null,
			...over
		}) as any;
	const lookup = {
		rip: (id: string) => (id === 'r1' ? (rip() as any) : undefined),
		transcode: (id: string | null) =>
			id === 't1' ? (transcode({ container: 'mkv', encoder: 'any_h265' }) as any) : undefined,
		samplePath: (s: any) => `sample/${s.id}.mkv`
	};
	const cols = sessionColumns(lookup);
	const cellOf = (id: string, s = session()) => cols.find((c) => c.id === id)!.cell(s);

	it('has the mockup columns in order', () => {
		expect(cols.map((c) => c.header)).toEqual([
			'Session',
			'Media',
			'Type',
			'Rip preset',
			'Transcode preset',
			'Output path (sample)'
		]);
	});

	it('shows the session name', () => {
		expect(cellOf('name')).toEqual({ text: 'Custom Plex 720p' });
	});

	it('shows media as a pill', () => {
		expect(cellOf('media')).toEqual({ text: 'Movie', pill: { tone: 'movie' } });
	});

	it('marks custom and built-in sessions with the Type tag', () => {
		expect(cellOf('type').pill).toEqual({ tone: 'custom' });
		expect(cellOf('type', session({ is_builtin: true })).pill).toEqual({ tone: 'builtin' });
	});

	it('names the rip preset with its summary under it', () => {
		expect(cellOf('rip')).toEqual({ text: 'Movie: Main Feature', sub: 'Main feature | Tracks' });
	});

	it('falls back to the preset id when the rip preset is missing', () => {
		expect(cellOf('rip', session({ rip_preset_id: 'gone' }))).toEqual({ text: 'gone' });
	});

	it('names the transcode preset with container and encoder under it', () => {
		expect(cellOf('transcode')).toEqual({ text: 'H.265 MKV', sub: 'MKV | Any GPU H.265' });
	});

	it('leaves the encoder out of the summary when the preset has none', () => {
		const bare = sessionColumns({
			...lookup,
			transcode: () => transcode({ container: 'iso', encoder: 'preset' }) as any
		});
		expect(bare.find((c) => c.id === 'transcode')!.cell(session()).sub).toBe('ISO');
	});

	it('says No transcode, muted, when the session has none or its preset is missing', () => {
		const none = { text: 'No transcode', muted: true };
		expect(cellOf('transcode', session({ transcode_preset_id: null }))).toEqual(none);
		expect(cellOf('transcode', session({ transcode_preset_id: 'gone' }))).toEqual(none);
	});

	it('shows the sample output path in monospace', () => {
		expect(cellOf('output')).toEqual({ text: 'sample/s1.mkv', mono: true });
	});
});
