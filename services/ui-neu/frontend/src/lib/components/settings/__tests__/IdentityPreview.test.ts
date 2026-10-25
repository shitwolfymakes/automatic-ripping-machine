import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, within } from '$lib/test-utils';
import IdentityPreview from '../IdentityPreview.svelte';
import { IDENTITY_METAS, IDENTITY_DEFAULTS } from '$lib/utils/__tests__/fixtures/identity-metas';

afterEach(() => cleanup());

const render = (kind: 'bluray' | 'dvd' | 'cd', over: Record<string, unknown> = {}) =>
	renderComponent(IdentityPreview, {
		props: { kind, values: { ...IDENTITY_DEFAULTS, ...over }, fields: IDENTITY_METAS }
	});
const pills = (row: HTMLElement) =>
	within(row)
		.queryAllByTestId('identity-preview-pill')
		.map((p) => [
			p.querySelector('.identity-preview-rank')?.textContent?.trim(),
			p.textContent?.replace(/\s+/g, ' ').trim()
		]);

describe('IdentityPreview', () => {
	it('renders the Blu-ray rows with ranked pills and trust text', () => {
		render('bluray');
		const panel = screen.getByTestId('identity-preview');
		expect(panel).toHaveAttribute('role', 'group');
		expect(panel).toHaveAttribute('aria-label', 'Identity preview');

		const disc = screen.getByTestId('identity-preview-disc');
		expect(disc).toHaveTextContent('Disc');
		expect(disc).toHaveTextContent('Disc title metadata and volume label, then TheDiscDB');

		const movie = screen.getByTestId('identity-preview-movie');
		expect(movie).toHaveTextContent('Movies');
		expect(pills(movie)).toEqual([
			['1', '1 TMDb'],
			['2', '2 OMDb']
		]);
		expect(movie).toHaveTextContent('Applies confident matches');

		const tv = screen.getByTestId('identity-preview-tv');
		expect(tv).toHaveTextContent('TV shows');
		expect(pills(tv).map((p) => p[1])).toEqual(['1 TMDb', '2 TVmaze', '3 TVDB']);
		expect(screen.queryByTestId('identity-preview-music')).not.toBeInTheDocument();
	});

	it('CD renders Disc and Music only', () => {
		render('cd');
		expect(screen.getByTestId('identity-preview-disc')).toHaveTextContent('Volume label and disc ID (track layout)');
		expect(pills(screen.getByTestId('identity-preview-music')).map((p) => p[1])).toEqual(['1 MusicBrainz']);
		expect(screen.queryByTestId('identity-preview-movie')).not.toBeInTheDocument();
		expect(screen.queryByTestId('identity-preview-tv')).not.toBeInTheDocument();
	});

	it('an empty list shows No sources on in place of the pills; a switch off reads per kind', () => {
		render('bluray', { movie_sources: [], movie_auto_apply: false, episode_auto_apply: false });
		const movie = screen.getByTestId('identity-preview-movie');
		expect(pills(movie)).toEqual([]);
		expect(movie).toHaveTextContent('No sources on');
		expect(movie).toHaveTextContent('Waits for review');
		// A TV match is never held back: off means every match is placed as a guess.
		expect(screen.getByTestId('identity-preview-tv')).toHaveTextContent('Places every match as a guess');
	});
});
