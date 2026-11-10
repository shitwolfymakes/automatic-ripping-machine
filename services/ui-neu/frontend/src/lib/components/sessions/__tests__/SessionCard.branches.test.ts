import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import SessionCard from '../SessionCard.svelte';

// Branch pins for SessionCard, beside SessionCard.svelte.test.ts.

vi.mock('$lib/api/encoders', () => ({
	fetchEncoders: () => Promise.resolve([])
}));

const joined = (over = {}) =>
	({
		id: 's1',
		name: 'Movies: Archive',
		media_type: 'movie',
		is_builtin: false,
		rip_preset_id: 'r1',
		transcode_preset_id: 't1',
		output_path_template: 'movies/{title} ({year}).{ext}',
		overrides_json: null,
		ripPreset: { id: 'r1', name: 'Movie: Main Feature', track_selection: 'main_feature', output_mode: 'tracks' },
		transcodePreset: { id: 't1', name: 'H.265 MKV', container: 'mkv', encoder: 'any_h265' },
		...over
	}) as any;

function renderCard(session: unknown) {
	return renderComponent(SessionCard, {
		session: session as never,
		onedit: vi.fn(),
		onclone: vi.fn(),
		ondelete: vi.fn()
	});
}

afterEach(cleanup);

describe('SessionCard media type pill', () => {
	it.each([
		['movie', 'Movie'],
		['tv', 'TV'],
		['music', 'Music'],
		['data', 'Data'],
		['iso', 'ISO']
	])('labels %s as %s and keeps the raw value in data-media', (media, label) => {
		const { container } = renderCard(joined({ media_type: media }));
		const pill = container.querySelector('.session-card-pill') as HTMLElement;
		expect(pill.textContent?.trim()).toBe(label);
		expect(pill.getAttribute('data-media')).toBe(media);
	});

	it('shows the raw value for a media type no table lists', () => {
		const { container } = renderCard(joined({ media_type: 'hologram' }));
		const pill = container.querySelector('.session-card-pill') as HTMLElement;
		expect(pill.textContent?.trim()).toBe('hologram');
		expect(pill.getAttribute('data-media')).toBe('hologram');
	});
});

describe('SessionCard rip cell', () => {
	it.each([
		['main_feature', 'Main feature'],
		['all_tracks', 'All tracks'],
		['archive', 'Archive'],
		['custom', 'Custom']
	])('labels track selection %s as %s', (value, label) => {
		renderCard(joined({ ripPreset: { id: 'r1', name: 'Rip', track_selection: value, output_mode: 'tracks' } }));
		expect(screen.getByText(`${label} | Tracks`)).toBeInTheDocument();
	});

	it('shows the raw value for a track selection no table lists', () => {
		renderCard(joined({ ripPreset: { id: 'r1', name: 'Rip', track_selection: 'sampler', output_mode: 'tracks' } }));
		expect(screen.getByText('sampler | Tracks')).toBeInTheDocument();
	});

	it('shows the rip preset id and a dash when the session has no rip preset', () => {
		renderCard(joined({ ripPreset: undefined, rip_preset_id: 'r-missing' }));
		expect(screen.getByText('r-missing')).toBeInTheDocument();
		expect(screen.getByText('-')).toBeInTheDocument();
	});
});

describe('SessionCard transcode cell', () => {
	it('shows "No transcode" when the session has no transcode preset', () => {
		renderCard(joined({ transcode_preset_id: null, transcodePreset: undefined }));
		expect(screen.getByText('No transcode')).toBeInTheDocument();
	});
});
