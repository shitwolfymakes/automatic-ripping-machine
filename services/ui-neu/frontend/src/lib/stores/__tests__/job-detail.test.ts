import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { JobView, TrackView } from '$lib/types/api.gen';

vi.mock('$lib/api/jobs', () => ({
	fetchJob: vi.fn(),
	fetchNamingPreview: vi.fn(),
	updateTrack: vi.fn(),
	resolveJob: vi.fn()
}));
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));

import { goto } from '$app/navigation';
import { fetchJob, fetchNamingPreview, resolveJob, updateTrack } from '$lib/api/jobs';
import { buildResolveBody } from '$lib/jobs/resolve';
import { ApiError } from '$lib/api/client';
import { createJob, createTrack, createJobDetail } from '$lib/__fixtures__/job';
import { JobDetail } from '../job-detail.svelte';

const mockFetchJob = vi.mocked(fetchJob);
const mockPreview = vi.mocked(fetchNamingPreview);
const mockUpdateTrack = vi.mocked(updateTrack);
const mockGoto = vi.mocked(goto);
const mockResolve = vi.mocked(resolveJob);

const previewOf = (...trackIds: string[]) =>
	({ job_output_dir: '', job_output_name: '', items: trackIds.map((track_id) => ({ track_id })) }) as never;

function newDetail(id = 'job_1') {
	return new JobDetail(() => id);
}

function detailWith(job: Partial<JobView> = {}, tracks: TrackView[] = []) {
	const d = newDetail();
	d.detail = createJobDetail({ ...job, tracks });
	return d;
}

beforeEach(() => {
	mockFetchJob.mockReset();
	mockPreview.mockReset();
	mockUpdateTrack.mockReset();
	mockGoto.mockReset();
	mockResolve.mockReset();
	mockFetchJob.mockResolvedValue(createJobDetail());
	mockPreview.mockResolvedValue(previewOf());
});

describe('JobDetail load', () => {
	it('starts loading with no job, no error and no preview', () => {
		const d = newDetail();
		expect(d.loading).toBe(true);
		expect(d.detail).toBeNull();
		expect(d.error).toBeNull();
		expect(d.previewItems).toEqual([]);
	});

	it('sets loading for the first load and clears it once the job arrives', async () => {
		const d = newDetail('job_7');
		d.loading = false;
		let during: boolean | undefined;
		mockFetchJob.mockImplementationOnce(async () => {
			during = d.loading;
			return createJobDetail();
		});
		await d.load();
		expect(during).toBe(true);
		expect(d.loading).toBe(false);
		expect(d.detail).not.toBeNull();
		expect(mockFetchJob).toHaveBeenCalledWith('job_7');
		expect(mockPreview).toHaveBeenCalledWith('job_7');
	});

	it('does not set loading on a later load', async () => {
		const d = newDetail();
		await d.load();
		let during: boolean | undefined;
		mockFetchJob.mockImplementationOnce(async () => {
			during = d.loading;
			return createJobDetail();
		});
		await d.load();
		expect(during).toBe(false);
	});

	it('loads and fetches the preview on a poll load', async () => {
		const d = newDetail();
		await d.load({ poll: true });
		expect(d.detail).not.toBeNull();
		expect(mockPreview).toHaveBeenCalledTimes(1);
	});

	it('keeps the Error a failed fetch threw', async () => {
		const d = newDetail();
		const err = new Error('boom');
		mockFetchJob.mockRejectedValueOnce(err);
		await d.load();
		expect(d.error).toBe(err);
		expect(d.loading).toBe(false);
		expect(mockGoto).not.toHaveBeenCalled();
	});

	it('wraps a non-Error failure in a generic Error', async () => {
		const d = newDetail();
		mockFetchJob.mockRejectedValueOnce('nope');
		await d.load();
		expect(d.error?.message).toBe('Failed to load job');
	});

	it('redirects to the dashboard when the message mentions 404', async () => {
		const d = newDetail();
		mockFetchJob.mockRejectedValueOnce(new Error('404 not found'));
		await d.load();
		expect(mockGoto).toHaveBeenCalledWith('/');
		expect(d.error).toBeNull();
		expect(d.loading).toBe(false);
	});

	it('clears an earlier error when the next load starts', async () => {
		const d = newDetail();
		mockFetchJob.mockRejectedValueOnce(new Error('boom'));
		await d.load();
		await d.load();
		expect(d.error).toBeNull();
	});
});

describe('JobDetail naming preview', () => {
	it('stores the preview items and keys them by track id', async () => {
		const d = newDetail();
		mockPreview.mockResolvedValueOnce(previewOf('t1', 't2'));
		await d.load();
		expect(d.previewItems).toHaveLength(2);
		expect([...d.previewByTrack.keys()]).toEqual(['t1', 't2']);
		expect(d.previewByTrack.get('t2')?.track_id).toBe('t2');
	});

	it('marks the preview unrouted on a 409, skips the next five poll loads and asks on the sixth', async () => {
		const d = newDetail();
		mockPreview.mockRejectedValueOnce(new ApiError(409, 'no route', null));
		await d.load();
		expect(mockPreview).toHaveBeenCalledTimes(1);
		for (let i = 0; i < 5; i++) await d.load({ poll: true });
		expect(mockPreview).toHaveBeenCalledTimes(1);
		await d.load({ poll: true });
		expect(mockPreview).toHaveBeenCalledTimes(2);
	});

	it('asks again on a non-poll load while unrouted', async () => {
		const d = newDetail();
		mockPreview.mockRejectedValueOnce(new ApiError(409, 'no route', null));
		await d.load();
		await d.load();
		expect(mockPreview).toHaveBeenCalledTimes(2);
	});

	it('leaves unrouted once a preview succeeds, so polls ask every time again', async () => {
		const d = newDetail();
		mockPreview.mockRejectedValueOnce(new ApiError(409, 'no route', null));
		await d.load();
		await d.load();
		await d.load({ poll: true });
		await d.load({ poll: true });
		expect(mockPreview).toHaveBeenCalledTimes(4);
	});

	it('clears the items on a non-409 failure without skipping later polls', async () => {
		const d = newDetail();
		mockPreview.mockResolvedValueOnce(previewOf('t1'));
		await d.load();
		mockPreview.mockRejectedValueOnce(new ApiError(500, 'bad', null));
		await d.load();
		expect(d.previewItems).toEqual([]);
		await d.load({ poll: true });
		expect(mockPreview).toHaveBeenCalledTimes(3);
	});

	it('treats a non-ApiError preview failure as not unrouted', async () => {
		const d = newDetail();
		mockPreview.mockRejectedValueOnce(new Error('network'));
		await d.load();
		await d.load({ poll: true });
		expect(mockPreview).toHaveBeenCalledTimes(2);
		expect(d.error).toBeNull();
	});
});

describe('JobDetail setExcluded', () => {
	it('updates the track then reloads the job', async () => {
		const d = newDetail('job_9');
		mockUpdateTrack.mockResolvedValueOnce(undefined as never);
		await d.setExcluded('t1', true);
		expect(mockUpdateTrack).toHaveBeenCalledWith('job_9', 't1', { excluded: true });
		expect(mockFetchJob).toHaveBeenCalledTimes(1);
	});

	it('reloads after a failure and still rejects to the caller', async () => {
		const d = newDetail();
		mockUpdateTrack.mockRejectedValueOnce(new Error('denied'));
		await expect(d.setExcluded('t1', false)).rejects.toThrow('denied');
		expect(mockFetchJob).toHaveBeenCalledTimes(1);
	});
});

describe('JobDetail derived values', () => {
	it('are empty before any job loads', () => {
		const d = newDetail();
		expect(d.canResolve).toBe(false);
		expect(d.canApply).toBe(false);
		expect(d.isVideoDisc).toBe(false);
		expect(d.isCdDisc).toBe(false);
		expect(d.musicTracks).toEqual([]);
		expect(d.tracksAreSeries).toBe(false);
		expect(d.handSetCount).toBe(0);
		expect(d.jobMeta).toEqual({});
		expect(d.rawMetadataPairs).toEqual([]);
		expect(d.previewByTrack.size).toBe(0);
	});

	it('reads canResolve and canApply from the job actions', () => {
		const base = createJob();
		const on = detailWith({ actions: { ...base.actions, can_resolve: true, can_apply: true } });
		expect(on.canResolve).toBe(true);
		expect(on.canApply).toBe(true);
		const off = detailWith({ actions: { ...base.actions, can_resolve: false, can_apply: false } });
		expect(off.canResolve).toBe(false);
		expect(off.canApply).toBe(false);
	});

	it.each([
		['dvd', true, false],
		['bluray', true, false],
		['cd', false, true],
		['data', false, false]
	])('classifies a %s disc', (disc_type, video, cd) => {
		const d = detailWith({ disc_type: disc_type as JobView['disc_type'] });
		expect(d.isVideoDisc).toBe(video);
		expect(d.isCdDisc).toBe(cd);
	});

	it('extracts the music tracks from the metadata', () => {
		const d = detailWith({ metadata_json: { music: { tracks: [{ title: 'One', length_ms: 60000 }] } } });
		expect(d.musicTracks).toHaveLength(1);
		expect(d.musicTracks[0].title).toBe('One');
	});

	it.each([
		['an episode role', { role: 'episode' }, 'movie', true],
		['an episode number', { role: 'main', episode_number: 3 }, 'movie', true],
		['no role on a tv job', { role: null }, 'tv', true],
		['no role on a movie job', { role: null }, 'movie', false],
		['a non-episode role on a tv job', { role: 'main' }, 'tv', false]
	])('tracksAreSeries for %s', (_name, track, media_type, expected) => {
		const d = detailWith({ media_type: media_type as JobView['media_type'] }, [
			createTrack(track as Partial<TrackView>)
		]);
		expect(d.tracksAreSeries).toBe(expected);
	});

	it('tracksAreSeries is false for a job with no tracks', () => {
		expect(detailWith({}, []).tracksAreSeries).toBe(false);
	});

	it('counts the tracks whose episode number or role was set by hand', () => {
		const d = detailWith({}, [
			createTrack({ id: 'a', identity_provenance: { role: 'manual' } }),
			createTrack({ id: 'b', identity_provenance: { episode_number: 'manual' } }),
			createTrack({ id: 'c', identity_provenance: { role: 'auto' } }),
			createTrack({ id: 'd', identity_provenance: null })
		]);
		expect(d.handSetCount).toBe(2);
	});

	it('reads the job metadata and its raw pairs', () => {
		const d = detailWith({
			metadata_json: { identity: { provider: 'tmdb', external_ids: { imdb: 'tt1' } }, extra: 1 }
		});
		expect(d.jobMeta.imdb_id).toBe('tt1');
		expect(d.rawMetadataPairs.map(([k]) => k)).toEqual(['identity', 'extra']);
	});

	it('isPostRip is false before any job loads', () => {
		expect(newDetail().isPostRip).toBe(false);
	});

	it.each([
		['created', false],
		['ripping', false],
		['ripped', true],
		['ripped_partial', true]
	])('isPostRip for a %s job is %s', (status, expected) => {
		expect(detailWith({ status: status as JobView['status'] }).isPostRip).toBe(expected);
	});

	it('has no raw pairs when the job has no metadata', () => {
		const d = detailWith({ metadata_json: null as never });
		expect(d.rawMetadataPairs).toEqual([]);
		expect(d.jobMeta).toEqual({});
	});
});

describe('JobDetail saveFact', () => {
	it('returns false and sends nothing when no job is loaded', async () => {
		const d = newDetail();
		expect(await d.saveFact('title', 'Dune')).toBe(false);
		expect(mockResolve).not.toHaveBeenCalled();
		expect(mockFetchJob).not.toHaveBeenCalled();
	});

	it('throws on a blank title before any request', async () => {
		const d = detailWith({ id: 'job_1' });
		await expect(d.saveFact('title', '   ')).rejects.toThrow('A title is required');
		expect(mockResolve).not.toHaveBeenCalled();
		expect(mockFetchJob).not.toHaveBeenCalled();
	});

	it('sends the resolve body, reloads the job and returns true for a TV season change', async () => {
		const d = detailWith({ id: 'job_1', media_type: 'tv', season: 1 });
		const job = d.detail!.job;
		mockResolve.mockResolvedValue({ job: { ...job, season: 2 } } as never);
		expect(await d.saveFact('season', '2')).toBe(true);
		expect(mockResolve).toHaveBeenCalledWith('job_1', buildResolveBody(job, 'season', '2'));
		expect(mockFetchJob).toHaveBeenCalledTimes(1);
	});

	it('returns false for a movie edit, still reloading the job', async () => {
		const d = detailWith({ id: 'job_1', media_type: 'movie' });
		const job = d.detail!.job;
		mockResolve.mockResolvedValue({ job: { ...job, title: 'Dune' } } as never);
		expect(await d.saveFact('title', 'Dune')).toBe(false);
		expect(mockResolve).toHaveBeenCalledWith('job_1', buildResolveBody(job, 'title', 'Dune'));
		expect(mockFetchJob).toHaveBeenCalledTimes(1);
	});
});
