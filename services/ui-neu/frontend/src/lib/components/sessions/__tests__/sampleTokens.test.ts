import { it, expect } from 'vitest';
import { resolveSample, MEDIA_SAMPLE } from '../sampleTokens';

it('substitutes movie tokens', () => {
	expect(resolveSample('movies/{title} ({year}).{ext}', 'movie')).toBe('movies/Fight Club (1999).mkv');
});
it('leaves unknown tokens for the type as-is is impossible — only valid tokens are sampled', () => {
	// music sample has artist/album; movie sample does not
	expect(resolveSample('{artist}/{album}', 'music')).toBe('Radiohead/OK Computer');
});
it('every declared token for a type has a sample value', () => {
	for (const [mt, map] of Object.entries(MEDIA_SAMPLE)) {
		for (const k of Object.keys(map)) expect(String((map as any)[k]).length).toBeGreaterThan(0);
	}
});

// The sample map MUST cover every output-path token the backend validator allows
// for each media type (path_template.py _ALLOWED_TOKENS_BY_MEDIA), or the card's
// recipe preview leaves real tokens like {show}/{disc} literally unsubstituted.
it('samples every authoritative token per media type', () => {
	const BACKEND_TOKENS: Record<string, string[]> = {
		movie: ['title', 'year', 'track', 'duration_human', 'transcode_slug', 'ext'],
		tv: ['show', 'year', 'season', 'disc', 'track', 'episode', 'episode_title', 'duration_human', 'transcode_slug', 'ext'],
		music: ['artist', 'album', 'disc', 'track', 'track_title', 'transcode_slug', 'ext'],
		data: ['title'],
		iso: ['title', 'year', 'ext']
	};
	for (const [mt, tokens] of Object.entries(BACKEND_TOKENS)) {
		for (const tok of tokens) {
			expect(tok in (MEDIA_SAMPLE as any)[mt], `MEDIA_SAMPLE.${mt} missing token {${tok}}`).toBe(true);
		}
	}
});

it('resolves a full TV template with no leftover tokens', () => {
	const out = resolveSample('{show} ({year})/Season {season}/{show} - S{season}D{disc}E{episode} ({duration_human}) - {transcode_slug}.{ext}', 'tv');
	expect(out).not.toMatch(/\{\w+\}/);
	expect(out).toContain('Breaking Bad');
});
