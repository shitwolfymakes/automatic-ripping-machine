import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

function jsonResponse(data: unknown, ok = true) {
	return { ok, status: ok ? 200 : 500, statusText: ok ? 'OK' : 'Error', json: () => Promise.resolve(data) };
}

import {
	updateTrackTitle, clearTrackTitle, updateTrack,
	fetchNamingPreview, validatePattern, fetchNamingVariables, namingPreview,
	resolveJob, applySession,
	// MISSING in v3
	toggleMultiTitle, tvdbMatch, fetchTvdbEpisodes, updateJobNaming
} from '../api/jobs';

beforeEach(() => mockFetch.mockReset());

// ---------------------------------------------------------------------------
// The bulk-PATCH delta: every single-track edit is wrapped into
//   PATCH /api/jobs/{job_id}  body: { tracks: [{ track_id, ... }] }
// ---------------------------------------------------------------------------

describe('updateTrackTitle (bulk-PATCH wrap)', () => {
	it('PATCHes /api/jobs/{id} wrapping the track into tracks[]', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ id: 'job_1' }));
		await updateTrackTitle('job_1', 'trk_2', { title: 'New Title', year: 1999 });
		expect(mockFetch).toHaveBeenCalledWith('/api/jobs/job_1', expect.objectContaining({
			method: 'PATCH',
			body: JSON.stringify({ tracks: [{ track_id: 'trk_2', title: 'New Title', year: 1999 }] })
		}));
	});
});

describe('clearTrackTitle (bulk-PATCH wrap, null=clear)', () => {
	it('PATCHes /api/jobs/{id} clearing override fields to null', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ id: 'job_1' }));
		await clearTrackTitle('job_1', 'trk_3');
		expect(mockFetch).toHaveBeenCalledWith('/api/jobs/job_1', expect.objectContaining({
			method: 'PATCH',
			body: JSON.stringify({
				tracks: [{ track_id: 'trk_3', title: null, year: null, imdb_id: null, poster_url: null }]
			})
		}));
	});
});

describe('updateTrack (bulk-PATCH wrap)', () => {
	it('PATCHes /api/jobs/{id} wrapping arbitrary track fields', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ id: 'job_1' }));
		await updateTrack('job_1', 'trk_2', { excluded: true, episode_number: 4 });
		expect(mockFetch).toHaveBeenCalledWith('/api/jobs/job_1', expect.objectContaining({
			method: 'PATCH',
			body: JSON.stringify({ tracks: [{ track_id: 'trk_2', excluded: true, episode_number: 4 }] })
		}));
	});
});

// ---------------------------------------------------------------------------
// Naming (EXISTS in v3, reshaped contracts)
// ---------------------------------------------------------------------------

describe('fetchNamingPreview', () => {
	it('GETs /api/jobs/{id}/naming-preview and returns the v3 envelope', async () => {
		const preview = {
			job_output_dir: 'Test Show/Season 01',
			job_output_name: 'Test Show S01E01',
			items: [{ track_id: 'trk_0', track_number: 0, output_path: 'Test Show/Season 01/Pilot.mkv' }]
		};
		mockFetch.mockResolvedValue(jsonResponse(preview));
		const result = await fetchNamingPreview('job_42');
		expect(mockFetch).toHaveBeenCalledWith('/api/jobs/job_42/naming-preview', expect.objectContaining({
			headers: expect.objectContaining({ 'Content-Type': 'application/json' })
		}));
		expect(result.job_output_name).toBe('Test Show S01E01');
		expect(result.items).toHaveLength(1);
	});
});

describe('namingPreview', () => {
	it('POSTs /api/naming/preview with template + media_type', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ rendered: 'The Matrix (1999)' }));
		const result = await namingPreview('{title} ({year})', 'movie', { title: 'The Matrix', year: '1999' });
		expect(mockFetch).toHaveBeenCalledWith('/api/naming/preview', expect.objectContaining({
			method: 'POST',
			body: JSON.stringify({
				template: '{title} ({year})',
				media_type: 'movie',
				has_transcode_preset: false,
				variables: { title: 'The Matrix', year: '1999' }
			})
		}));
		expect(result.rendered).toBe('The Matrix (1999)');
	});
});

describe('validatePattern', () => {
	it('POSTs /api/naming/validate with template + media_type', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ valid: false }));
		const result = await validatePattern('{title} {episde}', 'tv');
		expect(mockFetch).toHaveBeenCalledWith('/api/naming/validate', expect.objectContaining({
			method: 'POST',
			body: JSON.stringify({ template: '{title} {episde}', media_type: 'tv', has_transcode_preset: false })
		}));
		expect(result.valid).toBe(false);
	});
});

describe('fetchNamingVariables', () => {
	it('GETs /api/naming/variables and returns the grouped map', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ variables: { movie: [{ token: 'title', description: 'Title' }] } }));
		const result = await fetchNamingVariables();
		expect(result.variables.movie[0].token).toBe('title');
	});
});

// ---------------------------------------------------------------------------
// Identify / resolve + apply-session (EXISTS in v3)
// ---------------------------------------------------------------------------

describe('resolveJob', () => {
	it('POSTs /api/jobs/{id}/resolve with {title, year, metadata} (video case)', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ job: { id: 'job_1' }, fan_out: [] }));
		await resolveJob('job_1', { title: 'X', year: 2020, metadata: {} });
		expect(mockFetch).toHaveBeenCalledWith('/api/jobs/job_1/resolve', expect.objectContaining({
			method: 'POST',
			body: JSON.stringify({ title: 'X', year: 2020, disc_number: null, disc_total: null, metadata: {} })
		}));
	});

	it('POSTs the music case with a metadata payload and defaults year to null', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ job: { id: 'job_2' }, fan_out: [] }));
		await resolveJob('job_2', { title: 'Album', metadata: { artist: 'A', tracks: [{ title: 'T1' }] } });
		expect(mockFetch).toHaveBeenCalledWith('/api/jobs/job_2/resolve', expect.objectContaining({
			method: 'POST',
			body: JSON.stringify({ title: 'Album', year: null, disc_number: null, disc_total: null, metadata: { artist: 'A', tracks: [{ title: 'T1' }] } })
		}));
	});
});

describe('applySession', () => {
	it('POSTs /api/jobs/{id}/transcode with {session_id, overwrite:false} by default', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ collisions: [] }));
		await applySession('job_1', { session_id: 'ses_1' });
		expect(mockFetch).toHaveBeenCalledWith('/api/jobs/job_1/transcode', expect.objectContaining({
			method: 'POST',
			body: JSON.stringify({ session_id: 'ses_1', overwrite: false })
		}));
	});

	it('passes overwrite:true through', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ collisions: [] }));
		await applySession('job_1', { session_id: 'ses_1', overwrite: true });
		expect(mockFetch).toHaveBeenCalledWith('/api/jobs/job_1/transcode', expect.objectContaining({
			method: 'POST',
			body: JSON.stringify({ session_id: 'ses_1', overwrite: true })
		}));
	});
});

// ---------------------------------------------------------------------------
// MISSING in v3 — reject before any fetch
// ---------------------------------------------------------------------------

describe('MISSING in v3', () => {
	it.each([
		['toggleMultiTitle', () => toggleMultiTitle('job_1', true)],
		['tvdbMatch', () => tvdbMatch('job_1', { season: 2, apply: true })],
		['fetchTvdbEpisodes', () => fetchTvdbEpisodes('job_1', 1)],
		['updateJobNaming', () => updateJobNaming('job_1', { title_pattern_override: '{title}' })]
	])('%s rejects with /not yet available in v3/', async (_name, call) => {
		await expect(call()).rejects.toThrow(/not yet available in v3/);
		expect(mockFetch).not.toHaveBeenCalled();
	});
});
