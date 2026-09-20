import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import MusicSearch from './MusicSearch.svelte';
import { createJob, createTrack } from './__fixtures__/job';

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		// Test-only helper — not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});

vi.mock('$lib/api/jobs', () => ({
	searchMusicMetadata: vi.fn(),
	fetchMusicDetail: vi.fn(),
	resolveJob: vi.fn(() => Promise.resolve({ job: {}, fan_out: [] })),
	patchJob: vi.fn(() => Promise.resolve({}))
}));
import { searchMusicMetadata, fetchMusicDetail, resolveJob, patchJob } from '$lib/api/jobs';
const mockSearch = vi.mocked(searchMusicMetadata);
const mockDetail = vi.mocked(fetchMusicDetail);
const mockResolve = vi.mocked(resolveJob);
const mockPatchJob = vi.mocked(patchJob);

afterEach(() => { cleanup(); vi.clearAllMocks(); });

it('searches with track_count when "match track count" is on and discTracks present', async () => {
	mockSearch.mockResolvedValue({ candidates: [] });
	renderComponent(MusicSearch, {
		props: {
			job: createJob({ id: 'job_1', disc_type: 'cd', title: 'Abbey Road' }),
			discTracks: [createTrack(), createTrack({ id: 'trk_2', index: 1 })]
		}
	});
	await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
	await waitFor(() =>
		expect(mockSearch).toHaveBeenCalledWith('Abbey Road', expect.objectContaining({ track_count: 2 }))
	);
});

it('multi-disc apply writes only the held disc\'s tracks', async () => {
	mockSearch.mockResolvedValue({
		candidates: [{ title: 'The Wall', year: 1979, kind: 'music', poster_url: null, provider_id: 'rel-2' }]
	});
	mockDetail.mockResolvedValue({
		release_id: 'rel-2', title: 'The Wall', artist: 'Pink Floyd', year: 1979,
		poster_url: null, disc_count: 2, track_count: 4,
		tracks: [
			{ position: 1, title: 'In the Flesh?', length_ms: 213000, disc_number: 1 },
			{ position: 2, title: 'The Thin Ice', length_ms: 151000, disc_number: 1 },
			{ position: 1, title: 'Hey You', length_ms: 280000, disc_number: 2 },
			{ position: 2, title: 'Is There Anybody Out There?', length_ms: 152000, disc_number: 2 }
		]
	});
	const onapply = vi.fn();
	renderComponent(MusicSearch, {
		props: {
			job: createJob({ id: 'job_wall', disc_type: 'cd', title: 'The Wall', disc_number: 2 }),
			discTracks: [
				createTrack({ id: 'trk_d2_1', index: 0 }),
				createTrack({ id: 'trk_d2_2', index: 1 })
			],
			onapply
		}
	});
	await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
	await waitFor(() => screen.getByText('The Wall'));
	await fireEvent.click(screen.getByText('The Wall'));
	await waitFor(() => screen.getByText('Hey You'));
	await fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
	await waitFor(() => {
		const [, payload] = mockResolve.mock.calls[0] as unknown as [string, { metadata: { tracks: Array<{ title: string; disc_number: number | null }> } }];
		const titles = payload.metadata.tracks.map((t) => t.title);
		expect(titles).toEqual(['Hey You', 'Is There Anybody Out There?']);
		expect(titles).not.toContain('In the Flesh?');
		expect(onapply).toHaveBeenCalled();
	});
});

it('passes Type/Format/Country/Status filters to the search', async () => {
	mockSearch.mockResolvedValue({ candidates: [] });
	renderComponent(MusicSearch, {
		props: {
			job: createJob({ id: 'job_f', disc_type: 'cd', title: 'greatest hits' }),
			discTracks: []
		}
	});
	await fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'album' } });
	await fireEvent.change(screen.getByLabelText('Format'), { target: { value: 'CD' } });
	await fireEvent.input(screen.getByLabelText('Country'), { target: { value: 'GB' } });
	await fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'official' } });
	await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
	await waitFor(() =>
		expect(mockSearch).toHaveBeenCalledWith(
			'greatest hits',
			expect.objectContaining({ release_type: 'album', format: 'CD', country: 'GB', status: 'official' })
		)
	);
});

it('renders type/format/country badges on result cards', async () => {
	mockSearch.mockResolvedValue({
		candidates: [
			{
				title: 'Greatest Hits',
				year: 2025,
				kind: 'music',
				poster_url: null,
				provider_id: 'rel-7',
				release_type: 'Album',
				format: 'CD',
				country: 'GB',
				track_count: 17
			}
		]
	});
	renderComponent(MusicSearch, {
		props: { job: createJob({ id: 'job_b', disc_type: 'cd', title: 'greatest hits' }), discTracks: [] }
	});
	await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
	await waitFor(() => screen.getByText('Greatest Hits'));
	const badge = (text: string) =>
		screen.getAllByText(text).find((el) => el.tagName === 'SPAN' && el.className.includes('rounded-sm'));
	expect(badge('Album')).toBeInTheDocument();
	expect(badge('CD')).toBeInTheDocument();
	expect(screen.getByText('GB')).toBeInTheDocument();
	expect(badge('17 tracks')).toBeInTheDocument();
});

it('flips a result card to show its tracklist', async () => {
	mockSearch.mockResolvedValue({
		candidates: [
			{
				title: 'Greatest Hits',
				year: 2025,
				kind: 'music',
				poster_url: null,
				provider_id: 'rel-flip',
				track_count: 2
			}
		]
	});
	mockDetail.mockResolvedValue({
		release_id: 'rel-flip', title: 'Greatest Hits', artist: 'Metronomy', year: 2025,
		poster_url: null, disc_count: 1, track_count: 2,
		tracks: [
			{ position: 1, title: 'The Look', length_ms: 213000, disc_number: 1 },
			{ position: 2, title: 'The Bay', length_ms: 244000, disc_number: 1 }
		]
	});
	renderComponent(MusicSearch, {
		props: { job: createJob({ id: 'job_flip', disc_type: 'cd', title: 'greatest hits' }), discTracks: [] }
	});
	await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
	await waitFor(() => screen.getByText('Greatest Hits'));

	const flipBtn = screen.getByTitle('Flip to see tracklist');
	await fireEvent.click(flipBtn);
	await waitFor(() => expect(mockDetail).toHaveBeenCalledWith('rel-flip'));
	await waitFor(() => expect(screen.getByText('The Look')).toBeInTheDocument());

	// Flip back: the back-face track title goes away.
	const backBtn = screen.getByTitle('Flip back');
	await fireEvent.click(backBtn);
	await waitFor(() => expect(screen.queryByText('The Look')).not.toBeInTheDocument());
});

it('shows Disc Length + Match Length columns and a Total row when disc tracks are known', async () => {
	mockSearch.mockResolvedValue({
		candidates: [{ title: 'Abbey Road', year: 1969, kind: 'music', poster_url: null, provider_id: 'rel-cmp' }]
	});
	mockDetail.mockResolvedValue({
		release_id: 'rel-cmp', title: 'Abbey Road', artist: 'The Beatles', year: 1969,
		poster_url: null, disc_count: 1, track_count: 2,
		tracks: [
			{ position: 1, title: 'Come Together', length_ms: 259000, disc_number: 1 },
			{ position: 2, title: 'Something', length_ms: 182000, disc_number: 1 }
		]
	});
	renderComponent(MusicSearch, {
		props: {
			job: createJob({ id: 'job_cmp', disc_type: 'cd', title: 'Abbey Road' }),
			discTracks: [
				createTrack({ id: 'trk_c1', index: 0, expected_duration_seconds: 259 }),
				createTrack({ id: 'trk_c2', index: 1, expected_duration_seconds: 182 })
			]
		}
	});
	await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
	await waitFor(() => screen.getByText('Abbey Road'));
	await fireEvent.click(screen.getByText('Abbey Road'));
	await waitFor(() => screen.getByText('Come Together'));
	expect(screen.getByText('Disc Length')).toBeInTheDocument();
	expect(screen.getByText('Match Length')).toBeInTheDocument();
	expect(screen.getByText('Total')).toBeInTheDocument();
});

it('warns before applying a total-duration mismatch and applies on confirm', async () => {
	mockSearch.mockResolvedValue({
		candidates: [{ title: 'Wrong Release', year: 2000, kind: 'music', poster_url: null, provider_id: 'rel-mis' }]
	});
	mockDetail.mockResolvedValue({
		release_id: 'rel-mis', title: 'Wrong Release', artist: 'Someone', year: 2000,
		poster_url: null, disc_count: 1, track_count: 2,
		tracks: [
			{ position: 1, title: 'Track A', length_ms: 400000, disc_number: 1 },
			{ position: 2, title: 'Track B', length_ms: 400000, disc_number: 1 }
		]
	});
	renderComponent(MusicSearch, {
		props: {
			job: createJob({ id: 'job_mis', disc_type: 'cd', title: 'Wrong Release' }),
			discTracks: [
				createTrack({ id: 'trk_m1', index: 0, expected_duration_seconds: 100 }),
				createTrack({ id: 'trk_m2', index: 1, expected_duration_seconds: 100 })
			]
		}
	});
	await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
	await waitFor(() => screen.getByText('Wrong Release'));
	await fireEvent.click(screen.getByText('Wrong Release'));
	await waitFor(() => screen.getByText('Track A'));
	await fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
	await waitFor(() => screen.getByRole('button', { name: 'Apply anyway' }));
	expect(mockResolve).not.toHaveBeenCalled();
	await fireEvent.click(screen.getByRole('button', { name: 'Apply anyway' }));
	await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(1));
});

it('applies directly when totals match (no warning)', async () => {
	mockSearch.mockResolvedValue({
		candidates: [{ title: 'Right Release', year: 2000, kind: 'music', poster_url: null, provider_id: 'rel-ok' }]
	});
	mockDetail.mockResolvedValue({
		release_id: 'rel-ok', title: 'Right Release', artist: 'Someone', year: 2000,
		poster_url: null, disc_count: 1, track_count: 2,
		tracks: [
			{ position: 1, title: 'Track A', length_ms: 100000, disc_number: 1 },
			{ position: 2, title: 'Track B', length_ms: 100000, disc_number: 1 }
		]
	});
	renderComponent(MusicSearch, {
		props: {
			job: createJob({ id: 'job_ok', disc_type: 'cd', title: 'Right Release' }),
			discTracks: [
				createTrack({ id: 'trk_o1', index: 0, expected_duration_seconds: 100 }),
				createTrack({ id: 'trk_o2', index: 1, expected_duration_seconds: 100 })
			]
		}
	});
	await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
	await waitFor(() => screen.getByText('Right Release'));
	await fireEvent.click(screen.getByText('Right Release'));
	await waitFor(() => screen.getByText('Track A'));
	await fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
	await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(1));
	expect(screen.queryByRole('button', { name: 'Apply anyway' })).not.toBeInTheDocument();
});

it('previews the disc→release title mapping before applying', async () => {
	mockSearch.mockResolvedValue({
		candidates: [{ title: 'Abbey Road', year: 1969, kind: 'music', poster_url: null, provider_id: 'rel-map' }]
	});
	mockDetail.mockResolvedValue({
		release_id: 'rel-map', title: 'Abbey Road', artist: 'The Beatles', year: 1969,
		poster_url: null, disc_count: 1, track_count: 2,
		tracks: [
			{ position: 1, title: 'Come Together', length_ms: 259000, disc_number: 1 },
			{ position: 2, title: 'Something', length_ms: 182000, disc_number: 1 }
		]
	});
	renderComponent(MusicSearch, {
		props: {
			job: createJob({ id: 'job_map', disc_type: 'cd', title: 'Abbey Road' }),
			discTracks: [
				createTrack({ id: 'trk_0', kind: 'audio_track', index: 0, expected_duration_seconds: 259 }),
				createTrack({ id: 'trk_1', kind: 'audio_track', index: 1, expected_duration_seconds: 182 })
			]
		}
	});
	await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
	await waitFor(() => screen.getByText('Abbey Road'));
	await fireEvent.click(screen.getByText('Abbey Road'));
	await waitFor(() => screen.getByText('Come Together'));
	await fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
	// A preview appears with a confirm button; resolveJob NOT yet called.
	await waitFor(() => screen.getByRole('button', { name: 'Apply titles' }));
	expect(mockResolve).not.toHaveBeenCalled();
	expect(mockPatchJob).not.toHaveBeenCalled();
});

it('writes release titles onto the disc track rows on confirm', async () => {
	mockSearch.mockResolvedValue({
		candidates: [{ title: 'Abbey Road', year: 1969, kind: 'music', poster_url: null, provider_id: 'rel-map2' }]
	});
	mockDetail.mockResolvedValue({
		release_id: 'rel-map2', title: 'Abbey Road', artist: 'The Beatles', year: 1969,
		poster_url: null, disc_count: 1, track_count: 2,
		tracks: [
			{ position: 1, title: 'Come Together', length_ms: 259000, disc_number: 1 },
			{ position: 2, title: 'Something', length_ms: 182000, disc_number: 1 }
		]
	});
	const onapply = vi.fn();
	renderComponent(MusicSearch, {
		props: {
			job: createJob({ id: 'job_map2', disc_type: 'cd', title: 'Abbey Road' }),
			discTracks: [
				createTrack({ id: 'trk_0', kind: 'audio_track', index: 0, expected_duration_seconds: 259 }),
				createTrack({ id: 'trk_1', kind: 'audio_track', index: 1, expected_duration_seconds: 182 })
			],
			onapply
		}
	});
	await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
	await waitFor(() => screen.getByText('Abbey Road'));
	await fireEvent.click(screen.getByText('Abbey Road'));
	await waitFor(() => screen.getByText('Come Together'));
	await fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
	await fireEvent.click(await screen.findByRole('button', { name: 'Apply titles' }));
	await waitFor(() => {
		expect(mockResolve).toHaveBeenCalledTimes(1);
		expect(mockPatchJob).toHaveBeenCalledWith('job_map2', expect.objectContaining({
			tracks: expect.arrayContaining([
				expect.objectContaining({ track_id: 'trk_0', title: 'Come Together' }),
				expect.objectContaining({ track_id: 'trk_1', title: 'Something' })
			])
		}));
		expect(onapply).toHaveBeenCalled();
	});
});

it('still applies identity when there are no disc tracks (no mapping step)', async () => {
	mockSearch.mockResolvedValue({
		candidates: [{ title: 'Abbey Road', year: 1969, kind: 'music', poster_url: null, provider_id: 'rel-nomap' }]
	});
	mockDetail.mockResolvedValue({
		release_id: 'rel-nomap', title: 'Abbey Road', artist: 'The Beatles', year: 1969,
		poster_url: null, disc_count: 1, track_count: 1,
		tracks: [{ position: 1, title: 'Come Together', length_ms: 259000, disc_number: 1 }]
	});
	const onapply = vi.fn();
	renderComponent(MusicSearch, {
		props: { job: createJob({ id: 'job_nomap', disc_type: 'cd', title: 'Abbey Road' }), discTracks: [], onapply }
	});
	await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
	await waitFor(() => screen.getByText('Abbey Road'));
	await fireEvent.click(screen.getByText('Abbey Road'));
	await waitFor(() => screen.getByText('Come Together'));
	await fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
	await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(1));
	expect(screen.queryByRole('button', { name: 'Apply titles' })).not.toBeInTheDocument();
	expect(mockPatchJob).not.toHaveBeenCalled();
	expect(onapply).toHaveBeenCalled();
});

it('loads detail and applies the chosen release via resolveJob', async () => {
	mockSearch.mockResolvedValue({
		candidates: [{ title: 'Abbey Road', year: 1969, kind: 'music', poster_url: null, provider_id: 'rel-1' }]
	});
	mockDetail.mockResolvedValue({
		release_id: 'rel-1', title: 'Abbey Road', artist: 'The Beatles', year: 1969,
		poster_url: null, disc_count: 1, track_count: 1,
		tracks: [{ position: 1, title: 'Come Together', length_ms: 259000, disc_number: 1 }]
	});
	const onapply = vi.fn();
	renderComponent(MusicSearch, {
		props: { job: createJob({ id: 'job_9', disc_type: 'cd', title: 'Abbey Road' }), discTracks: [], onapply }
	});
	await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
	await waitFor(() => screen.getByText('Abbey Road'));
	await fireEvent.click(screen.getByText('Abbey Road'));
	await waitFor(() => screen.getByText('Come Together'));
	await fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
	await waitFor(() => {
		expect(mockResolve).toHaveBeenCalledWith('job_9', expect.objectContaining({
			title: 'Abbey Road',
			metadata: expect.objectContaining({ artist: 'The Beatles', album: 'Abbey Road' })
		}));
		expect(onapply).toHaveBeenCalled();
	});
});

describe('guest write-control gating', () => {
	afterEach(async () => {
		cleanup();
		vi.clearAllMocks();
		const auth = (await import('$lib/stores/auth')) as unknown as {
			__setRole: (r: string | null) => void;
		};
		auth.__setRole('admin');
	});

	it('hides the Apply button for guests', async () => {
		const auth = (await import('$lib/stores/auth')) as unknown as {
			__setRole: (r: string | null) => void;
		};
		auth.__setRole('guest');
		mockSearch.mockResolvedValue({
			candidates: [{ title: 'Abbey Road', year: 1969, kind: 'music', poster_url: null, provider_id: 'rel-1' }]
		});
		mockDetail.mockResolvedValue({
			release_id: 'rel-1', title: 'Abbey Road', artist: 'The Beatles', year: 1969,
			poster_url: null, disc_count: 1, track_count: 1,
			tracks: [{ position: 1, title: 'Come Together', length_ms: 259000, disc_number: 1 }]
		});
		renderComponent(MusicSearch, {
			props: { job: createJob({ id: 'job_9', disc_type: 'cd', title: 'Abbey Road' }), discTracks: [] }
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
		await waitFor(() => screen.getByText('Abbey Road'));
		await fireEvent.click(screen.getByText('Abbey Road'));
		await waitFor(() => screen.getByText('Come Together'));
		expect(screen.queryByRole('button', { name: 'Apply' })).not.toBeInTheDocument();
	});

	it('shows the Apply button for admins', async () => {
		mockSearch.mockResolvedValue({
			candidates: [{ title: 'Abbey Road', year: 1969, kind: 'music', poster_url: null, provider_id: 'rel-1' }]
		});
		mockDetail.mockResolvedValue({
			release_id: 'rel-1', title: 'Abbey Road', artist: 'The Beatles', year: 1969,
			poster_url: null, disc_count: 1, track_count: 1,
			tracks: [{ position: 1, title: 'Come Together', length_ms: 259000, disc_number: 1 }]
		});
		renderComponent(MusicSearch, {
			props: { job: createJob({ id: 'job_9', disc_type: 'cd', title: 'Abbey Road' }), discTracks: [] }
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
		await waitFor(() => screen.getByText('Abbey Road'));
		await fireEvent.click(screen.getByText('Abbey Road'));
		await waitFor(() => screen.getByText('Come Together'));
		expect(screen.getByRole('button', { name: 'Apply' })).toBeInTheDocument();
	});
});
