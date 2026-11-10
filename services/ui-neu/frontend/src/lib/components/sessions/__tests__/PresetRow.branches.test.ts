import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import PresetRow from '../PresetRow.svelte';

// Branch pins for PresetRow, beside PresetRow.svelte.test.ts. Branches left
// open, because the rendered component cannot reach them:
// - The `?? '-'` fallback in each humanizer (media type, track selection,
//   identification mode, tool, container): every field they read is a
//   required, non-null string on RipPresetView and TranscodePresetView, so
//   the null and undefined outcomes never occur. Only the unknown-value
//   default (the raw value shown) is exercised.

vi.mock('$lib/api/encoders', () => ({
	fetchEncoders: () =>
		Promise.resolve([
			{
				id: 'any_h265',
				label: 'Any GPU H.265',
				group: 'any',
				engine: 'handbrake',
				kind: 'any',
				vendor: null,
				codec: 'h265',
				available: true,
				reason: null
			}
		])
}));

const ripPreset = (over = {}) => ({
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

const transcodePreset = (over = {}) => ({
	id: 't1',
	name: 'H.265 MKV',
	media_type: 'movie' as const,
	is_builtin: false,
	tool: 'handbrake' as const,
	preset_ref: null,
	preset_json: null,
	container: 'mkv' as const,
	encoder: 'any_h265',
	extra_args: null,
	created_by_user_id: null,
	created_at: null,
	updated_at: null,
	...over
});

function renderRow(kind: 'rip' | 'transcode', preset: unknown, usedBy = 0, handlers = {}) {
	return renderComponent(PresetRow, {
		kind,
		preset: preset as never,
		usedBy,
		onview: vi.fn(),
		onedit: vi.fn(),
		onclone: vi.fn(),
		ondelete: vi.fn(),
		...handlers
	});
}

afterEach(cleanup);

describe('PresetRow media type pill', () => {
	it.each([
		['movie', 'Movie'],
		['tv', 'TV'],
		['music', 'Music'],
		['data', 'Data'],
		['iso', 'ISO']
	])('labels %s as %s and keeps the raw value in data-media', (media, label) => {
		const { container } = renderRow('rip', ripPreset({ media_type: media, name: 'Zed' }));
		const pill = container.querySelector('.preset-row-pill') as HTMLElement;
		expect(pill.textContent?.trim()).toBe(label);
		expect(pill.getAttribute('data-media')).toBe(media);
	});

	it('shows the raw value for a media type no table lists', () => {
		const { container } = renderRow('rip', ripPreset({ media_type: 'hologram' }));
		const pill = container.querySelector('.preset-row-pill') as HTMLElement;
		expect(pill.textContent?.trim()).toBe('hologram');
		expect(pill.getAttribute('data-media')).toBe('hologram');
	});
});

describe('PresetRow rip summary', () => {
	it.each([
		['main_feature', 'Main feature'],
		['all_tracks', 'All tracks'],
		['archive', 'Archive'],
		['custom', 'Custom']
	])('labels track selection %s as %s', (value, label) => {
		renderRow('rip', ripPreset({ track_selection: value }));
		expect(screen.getByText(`${label} | ID required | Tracks`)).toBeInTheDocument();
	});

	it.each([
		['required', 'ID required'],
		['skip', 'ID skip'],
		['deferred_placeholder', 'ID deferred']
	])('labels identification mode %s as %s', (value, label) => {
		renderRow('rip', ripPreset({ identification_mode: value }));
		expect(screen.getByText(`Main feature | ${label} | Tracks`)).toBeInTheDocument();
	});

	it('shows raw values for a track selection and identification mode no table lists', () => {
		renderRow('rip', ripPreset({ track_selection: 'sampler', identification_mode: 'psychic' }));
		expect(screen.getByText('sampler | psychic | Tracks')).toBeInTheDocument();
	});
});

describe('PresetRow transcode summary', () => {
	it.each([
		['handbrake', 'HandBrake'],
		['abcde', 'abcde'],
		['none', 'None']
	])('labels tool %s as %s', async (value, label) => {
		renderRow('transcode', transcodePreset({ tool: value }));
		await waitFor(() => expect(screen.getByText(`${label} | MKV | Any GPU H.265`)).toBeInTheDocument());
	});

	it.each([
		['mkv', 'MKV'],
		['mp4', 'MP4'],
		['webm', 'WebM'],
		['flac', 'FLAC'],
		['mp3', 'MP3'],
		['ogg', 'OGG'],
		['iso', 'ISO'],
		['none', 'None']
	])('labels container %s as %s', async (value, label) => {
		renderRow('transcode', transcodePreset({ container: value }));
		await waitFor(() => expect(screen.getByText(`HandBrake | ${label} | Any GPU H.265`)).toBeInTheDocument());
	});

	it('drops an empty encoder label out of the line', () => {
		renderRow('transcode', transcodePreset({ encoder: '' }));
		expect(screen.getByText('HandBrake | MKV')).toBeInTheDocument();
	});

	it('shows raw values for a tool and container no table lists', async () => {
		renderRow('transcode', transcodePreset({ tool: 'ffmpeg', container: 'avi' }));
		await waitFor(() => expect(screen.getByText('ffmpeg | avi | Any GPU H.265')).toBeInTheDocument());
	});
});

describe('PresetRow delete button', () => {
	it('is disabled with the built-in reason for a built-in', () => {
		renderRow('rip', ripPreset({ is_builtin: true }), 0);
		const del = screen.getByRole('button', { name: 'Delete' }) as HTMLButtonElement;
		expect(del.disabled).toBe(true);
		expect(del.getAttribute('title')).toBe('Built-in preset: clone to edit or remove');
	});

	it('is disabled with the in-use reason for a custom preset in use', () => {
		renderRow('rip', ripPreset(), 3);
		const del = screen.getByRole('button', { name: 'Delete' }) as HTMLButtonElement;
		expect(del.disabled).toBe(true);
		expect(del.getAttribute('title')).toBe('Used by 3 session(s): repoint them first');
	});

	it('is enabled with no title for an unused custom preset', () => {
		renderRow('rip', ripPreset(), 0);
		const del = screen.getByRole('button', { name: 'Delete' }) as HTMLButtonElement;
		expect(del.disabled).toBe(false);
		expect(del.hasAttribute('title')).toBe(false);
	});
});

describe('PresetRow View and Edit', () => {
	it('reads View and calls onview for a built-in', async () => {
		const onview = vi.fn();
		const onedit = vi.fn();
		renderRow('rip', ripPreset({ is_builtin: true }), 0, { onview, onedit });
		await fireEvent.click(screen.getByRole('button', { name: 'View' }));
		expect(onview).toHaveBeenCalledTimes(1);
		expect(onedit).not.toHaveBeenCalled();
	});

	it('reads Edit and calls onedit for a custom preset', async () => {
		const onview = vi.fn();
		const onedit = vi.fn();
		renderRow('rip', ripPreset(), 0, { onview, onedit });
		await fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
		expect(onedit).toHaveBeenCalledTimes(1);
		expect(onview).not.toHaveBeenCalled();
	});
});
