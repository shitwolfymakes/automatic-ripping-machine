import { it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
vi.mock('$lib/api/sessions', () => ({ previewTemplate: vi.fn() }));
import { previewTemplate } from '$lib/api/sessions';
import OutputPathField from '../OutputPathField.svelte';

afterEach(cleanup);

it('shows only the valid tokens for the media type', () => {
	renderComponent(OutputPathField, { value: '', mediaType: 'music', onchange: vi.fn() });
	expect(screen.getByRole('button', { name: '{artist}' })).toBeInTheDocument();
	expect(screen.queryByRole('button', { name: '{season}' })).not.toBeInTheDocument(); // tv-only
});

it('TV shows show/disc tokens and not title', () => {
	renderComponent(OutputPathField, { value: '', mediaType: 'tv', onchange: vi.fn() });
	expect(screen.getByRole('button', { name: '{show}' })).toBeInTheDocument();
	expect(screen.getByRole('button', { name: '{disc}' })).toBeInTheDocument();
	expect(screen.queryByRole('button', { name: '{title}' })).not.toBeInTheDocument();
});

it('clicking a token chip appends it and fires onchange', async () => {
	const onchange = vi.fn();
	renderComponent(OutputPathField, { value: 'movies/', mediaType: 'movie', onchange });
	await fireEvent.click(screen.getByRole('button', { name: '{title}' }));
	expect(onchange).toHaveBeenCalledWith('movies/{title}');
});

it('renders the live preview from previewTemplate (response.expansion)', async () => {
	vi.mocked(previewTemplate).mockResolvedValue({ expansion: 'movies/Fight Club (1999).mkv' } as any);
	renderComponent(OutputPathField, { value: 'movies/{title} ({year}).{ext}', mediaType: 'movie', onchange: vi.fn() });
	await waitFor(() => expect(screen.getByText('movies/Fight Club (1999).mkv')).toBeInTheDocument());
	// request body is { template, media_type, has_transcode_preset? }
	expect(previewTemplate).toHaveBeenCalledWith(expect.objectContaining({ template: 'movies/{title} ({year}).{ext}', media_type: 'movie' }));
});

it('surfaces an error when preview rejects (invalid token -> 4xx throws)', async () => {
	vi.mocked(previewTemplate).mockRejectedValueOnce(new Error('unknown token {bogus}'));
	renderComponent(OutputPathField, { value: 'x/{bogus}', mediaType: 'movie', onchange: vi.fn() });
	await waitFor(() => expect(screen.getByText(/unknown token/i)).toBeInTheDocument());
});
