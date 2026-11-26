import { describe, it, expect, vi, beforeEach } from 'vitest';

const fetchJobMock = vi.fn();
const fetchNamingPreviewMock = vi.fn();
const fetchSessionsMock = vi.fn();
vi.mock('$lib/api/jobs', () => ({
	fetchJob: (...a: unknown[]) => fetchJobMock(...a),
	fetchNamingPreview: (...a: unknown[]) => fetchNamingPreviewMock(...a)
}));
vi.mock('$lib/api/sessions', () => ({
	fetchSessions: (...a: unknown[]) => fetchSessionsMock(...a)
}));

import { DiscReviewData } from '$lib/stores/disc-review-data.svelte';

const DETAIL = { job: { id: 'j1' }, tracks: [] };
const PREVIEW = {
	items: [
		{ track_id: 't1', output_name: 'A.mkv' },
		{ track_id: 't2', output_name: 'B.mkv' }
	]
};

beforeEach(() => {
	fetchJobMock.mockReset();
	fetchNamingPreviewMock.mockReset();
	fetchSessionsMock.mockReset();
});

describe('DiscReviewData', () => {
	it('starts empty and loading', () => {
		const data = new DiscReviewData(() => 'j1');
		expect(data.detail).toBeNull();
		expect(data.fileNames.size).toBe(0);
		expect(data.initialLoading).toBe(true);
		expect(data.sessions).toEqual([]);
		expect(data.sessionNames.size).toBe(0);
	});

	it('loadDetail with no job id fetches nothing and stays loading', async () => {
		const data = new DiscReviewData(() => undefined);
		await data.loadDetail();
		expect(fetchJobMock).not.toHaveBeenCalled();
		expect(fetchNamingPreviewMock).not.toHaveBeenCalled();
		expect(data.initialLoading).toBe(true);
	});

	it('loadDetail stores the detail, lowers loading and maps track ids to file names', async () => {
		fetchJobMock.mockResolvedValue(DETAIL);
		fetchNamingPreviewMock.mockResolvedValue(PREVIEW);
		const data = new DiscReviewData(() => 'j1');
		await data.loadDetail();
		expect(data.detail).toEqual(DETAIL);
		expect(data.initialLoading).toBe(false);
		expect(data.fileNames.get('t1')).toBe('A.mkv');
		expect(data.fileNames.get('t2')).toBe('B.mkv');
		expect(data.fileNames.size).toBe(2);
	});

	it('loadDetail gives an empty map when the preview has no items', async () => {
		fetchJobMock.mockResolvedValue(DETAIL);
		fetchNamingPreviewMock.mockResolvedValue({});
		const data = new DiscReviewData(() => 'j1');
		await data.loadDetail();
		expect(data.fileNames.size).toBe(0);
	});

	it('loadDetail fetches for the id the getter returns at call time', async () => {
		fetchJobMock.mockResolvedValue(DETAIL);
		fetchNamingPreviewMock.mockResolvedValue(PREVIEW);
		let id = 'first';
		const data = new DiscReviewData(() => id);
		id = 'second';
		await data.loadDetail();
		expect(fetchJobMock).toHaveBeenCalledWith('second');
		expect(fetchNamingPreviewMock).toHaveBeenCalledWith('second');
	});

	it('loadDetail keeps the earlier detail when a later job fetch fails, and still fetches the preview', async () => {
		fetchJobMock.mockResolvedValueOnce(DETAIL).mockRejectedValueOnce(new Error('down'));
		fetchNamingPreviewMock.mockResolvedValue(PREVIEW);
		const data = new DiscReviewData(() => 'j1');
		await data.loadDetail();
		await data.loadDetail();
		expect(data.detail).toEqual(DETAIL);
		expect(data.initialLoading).toBe(false);
		expect(fetchNamingPreviewMock).toHaveBeenCalledTimes(2);
	});

	it('loadDetail leaves the detail null and lowers loading when the first job fetch fails', async () => {
		fetchJobMock.mockRejectedValue(new Error('down'));
		fetchNamingPreviewMock.mockRejectedValue(new Error('409'));
		const data = new DiscReviewData(() => 'j1');
		await data.loadDetail();
		expect(data.detail).toBeNull();
		expect(data.initialLoading).toBe(false);
	});

	it('loadDetail empties the file names when a later preview fetch fails', async () => {
		fetchJobMock.mockResolvedValue(DETAIL);
		fetchNamingPreviewMock.mockResolvedValueOnce(PREVIEW).mockRejectedValueOnce(new Error('409'));
		const data = new DiscReviewData(() => 'j1');
		await data.loadDetail();
		expect(data.fileNames.size).toBe(2);
		await data.loadDetail();
		expect(data.fileNames.size).toBe(0);
	});

	it('loadSessions stores the sessions and maps ids to names', async () => {
		const sessions = [
			{ id: 's1', name: 'One' },
			{ id: 's2', name: 'Two' }
		];
		fetchSessionsMock.mockResolvedValue(sessions);
		const data = new DiscReviewData(() => 'j1');
		await data.loadSessions();
		expect(data.sessions).toEqual(sessions);
		expect(data.sessionNames.get('s1')).toBe('One');
		expect(data.sessionNames.get('s2')).toBe('Two');
	});

	it('loadSessions empties the sessions and names when a later fetch fails', async () => {
		fetchSessionsMock.mockResolvedValueOnce([{ id: 's1', name: 'One' }]).mockRejectedValueOnce(new Error('down'));
		const data = new DiscReviewData(() => 'j1');
		await data.loadSessions();
		await data.loadSessions();
		expect(data.sessions).toEqual([]);
		expect(data.sessionNames.size).toBe(0);
	});
});
