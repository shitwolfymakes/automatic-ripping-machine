import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/testing/render';
vi.mock('$lib/api/sessions', () => ({
	createSession: vi.fn(),
	updateSession: vi.fn(),
	previewTemplate: vi.fn().mockResolvedValue({ expansion: 'p' })
}));
import { createSession, updateSession, previewTemplate } from '$lib/api/sessions';
import SessionBuilder from './SessionBuilderHarness.svelte';
import { ALL_MUSIC_TAGS } from '$lib/sessions/music-tags';

// The Music file tags field: shown for a music session that encodes, saved
// with it, and left out of every other session's request.

const preset = (id: string, mt: string) => ({ id, name: `preset ${id}`, media_type: mt }) as any;
const props = (over = {}) => ({
	session: null,
	ripPresets: [preset('r-movie', 'movie'), preset('r-music', 'music')],
	transcodePresets: [preset('t-movie', 'movie'), preset('t-flac', 'music')],
	oncreaterip: vi.fn(),
	oncreatetranscode: vi.fn(),
	onsaved: vi.fn(),
	...over
});

const musicSession = (over = {}) =>
	({
		id: 'ses-music',
		name: 'FLAC, no cover',
		media_type: 'music',
		is_builtin: false,
		rip_preset_id: 'r-music',
		transcode_preset_id: 't-flac',
		output_path_template: '{artist}/{album}/{track}.{ext}',
		overrides_json: null,
		music_tag_fields: ['artist', 'title', 'cover'],
		...over
	}) as any;

const box = (name: string) => screen.getByRole('checkbox', { name }) as HTMLInputElement;
const tagsField = () => screen.queryByTestId('sb-music-tags');
const submit = () => fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

beforeEach(() => {
	vi.mocked(createSession).mockReset();
	vi.mocked(updateSession).mockReset();
	vi.mocked(previewTemplate).mockResolvedValue({ expansion: 'p' } as any);
});

afterEach(cleanup);

describe('SessionBuilder music file tags', () => {
	it('shows the session choice and saves what is ticked', async () => {
		vi.mocked(updateSession).mockResolvedValue(musicSession());
		renderComponent(SessionBuilder, props({ session: musicSession() }));

		expect(screen.getByRole('group', { name: 'Music file tags' })).toHaveAttribute(
			'aria-describedby',
			'sb-music-tags-help'
		);
		expect(box('Artist').checked).toBe(true);
		expect(box('Album').checked).toBe(false);
		await fireEvent.click(box('Cover art'));
		await fireEvent.click(box('Album'));
		await submit();

		await waitFor(() =>
			expect(updateSession).toHaveBeenCalledWith(
				'ses-music',
				expect.objectContaining({ music_tag_fields: ['artist', 'album', 'title'] })
			)
		);
	});

	it('offers every tag, ticked, on a new music session and creates it with them', async () => {
		vi.mocked(createSession).mockResolvedValue(musicSession());
		renderComponent(SessionBuilder, props());
		expect(tagsField()).toBeNull();

		await fireEvent.click(screen.getByRole('button', { name: 'Music' }));
		await fireEvent.input(screen.getByLabelText(/session name/i), { target: { value: 'Music' } });
		await fireEvent.change(screen.getByLabelText(/^rip preset/i), { target: { value: 'r-music' } });
		await fireEvent.change(screen.getByLabelText(/^transcode preset/i), { target: { value: 't-flac' } });
		await fireEvent.input(screen.getByLabelText(/^output path/i), { target: { value: '{album}/{track}.{ext}' } });

		expect(tagsField()).not.toBeNull();
		for (const el of screen.getAllByRole('checkbox')) expect((el as HTMLInputElement).checked).toBe(true);
		await submit();

		await waitFor(() =>
			expect(createSession).toHaveBeenCalledWith(
				expect.objectContaining({ media_type: 'music', music_tag_fields: [...ALL_MUSIC_TAGS] })
			)
		);
	});

	it('hides the field for a rip-only music session, which writes no tags', () => {
		renderComponent(SessionBuilder, props({ session: musicSession({ transcode_preset_id: null }) }));
		expect(tagsField()).toBeNull();
	});

	it('hides the field for a movie session and sends no tags with it', async () => {
		const movie = musicSession({
			id: 'ses-movie',
			media_type: 'movie',
			rip_preset_id: 'r-movie',
			transcode_preset_id: 't-movie',
			output_path_template: '{title}.{ext}'
		});
		vi.mocked(updateSession).mockResolvedValue(movie);
		renderComponent(SessionBuilder, props({ session: movie }));

		expect(tagsField()).toBeNull();
		await submit();

		await waitFor(() => expect(updateSession).toHaveBeenCalledOnce());
		expect(vi.mocked(updateSession).mock.calls[0][1]).not.toHaveProperty('music_tag_fields');
	});

	it('locks the checkboxes on a built-in session', () => {
		renderComponent(SessionBuilder, props({ session: musicSession({ is_builtin: true }) }));
		for (const el of screen.getAllByRole('checkbox')) expect(el).toBeDisabled();
	});
});
