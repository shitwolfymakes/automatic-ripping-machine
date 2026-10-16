import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import DiscReviewWidget from '../DiscReviewWidget.svelte';
import { createJob, createJobDetail, createTrack } from '../__fixtures__/job';

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
	fetchJob: vi.fn(() =>
		Promise.resolve({
			...createJobDetail({ tracks: [createTrack({ id: 'trk_1', index: 0, source_ref: 't00.mkv', title: 'Main' })] }),
			job: createJob({ title: 'Test Movie', disc_type: 'bluray' })
		})
	),
	abandonJob: vi.fn(() => Promise.resolve(createJob())),
	deleteJob: vi.fn(() => Promise.resolve()),
	startWaitingJob: vi.fn(() => Promise.resolve(createJob())),
	resolveJob: vi.fn(() => Promise.resolve({})),
	acceptIdentitySuggestion: vi.fn(() => Promise.resolve({ job: {}, fan_out: [] })),
	updateTrack: vi.fn(() => Promise.resolve(createJob())),
	updateJobTitle: vi.fn(() => Promise.resolve(createJob())),
	updateJobConfig: vi.fn(() => Promise.resolve(createJob())),
	updateTrackTitle: vi.fn(() => Promise.resolve(createJob())),
	clearTrackTitle: vi.fn(() => Promise.resolve(createJob())),
	searchMetadata: vi.fn(),
	fetchMediaDetail: vi.fn(),
	searchMusicMetadata: vi.fn(),
	fetchMusicDetail: vi.fn(),
	fetchNamingVariables: vi.fn(() => Promise.resolve({ variables: {} })),
	namingPreview: vi.fn(() => Promise.resolve({ rendered: '' })),
	validatePattern: vi.fn(() => Promise.resolve({ valid: true }))
}));

vi.mock('$lib/api/settings', () => ({
	fetchTranscoderPresets: vi.fn(() => Promise.resolve(null))
}));

vi.mock('$lib/api/sessions', () => ({
	fetchSessions: vi.fn(() => Promise.resolve([]))
}));

vi.mock('$lib/api/iso', () => ({
	cancelIsoRip: vi.fn(() => Promise.resolve())
}));

function renderWidget(overrides = {}, isoSources: Record<string, string> | null = null) {
	return renderComponent(DiscReviewWidget, {
		props: {
			job: createJob({ status: 'identified', ...overrides }),
			driveNames: {},
			paused: false,
			isoSources
		}
	});
}

describe('DiscReviewWidget', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	describe('tracks', () => {
		it('renders the v3 tracks table from data.tracks', async () => {
			renderWidget();
			// The tracks table now lives at the bottom of the Info tab — open it first.
			await waitFor(() => expect(screen.getByRole('button', { name: 'Info' })).toBeInTheDocument());
			await fireEvent.click(screen.getByRole('button', { name: 'Info' }));
			await waitFor(() => {
				expect(screen.getByText('Main')).toBeInTheDocument();
				expect(screen.getByText('t00.mkv')).toBeInTheDocument();
			});
		});
	});

	describe('action buttons', () => {
		it('renders Cancel before the (enabled) Start rip control for awaiting_review', async () => {
			renderWidget({ status: 'awaiting_review' });
			await waitFor(() => expect(screen.getByText('Start rip')).toBeInTheDocument());
			const cancelBtn = screen.getByText('Cancel');
			const startBtn = screen.getByText('Start rip');
			// Start rip is the rightmost action — Cancel comes before it.
			expect(cancelBtn.compareDocumentPosition(startBtn) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
			expect(startBtn).not.toBeDisabled();
		});

		it('offers Delete instead of Cancel once the rip has finished', async () => {
			const { deleteJob, fetchJob } = await import('$lib/api/jobs');
			const done = createJob({ status: 'ripped_awaiting_identify' });
			const original = vi.mocked(fetchJob).getMockImplementation();
			vi.mocked(fetchJob).mockResolvedValue({ ...createJobDetail(), job: done });
			try {
				const ondismiss = vi.fn();
				renderComponent(DiscReviewWidget, { props: { job: done, driveNames: {}, paused: false, ondismiss } });
				const deleteBtn = await screen.findByRole('button', { name: 'Delete' });
				expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument();
				await fireEvent.click(deleteBtn);
				expect(
					screen.getByText('Delete this job? The raw files stay on disk. This cannot be undone.')
				).toBeInTheDocument();
				const buttons = screen.getAllByRole('button', { name: 'Delete' });
				await fireEvent.click(buttons[buttons.length - 1]);
				await waitFor(() => expect(deleteJob).toHaveBeenCalledWith('job_1'));
				await waitFor(() => expect(ondismiss).toHaveBeenCalled());
			} finally {
				vi.mocked(fetchJob).mockImplementation(original!);
			}
		});

		it('keeps the card and shows the error when Cancel fails', async () => {
			const { abandonJob } = await import('$lib/api/jobs');
			vi.mocked(abandonJob).mockRejectedValueOnce(new Error('409 job cannot be abandoned'));
			const ondismiss = vi.fn();
			renderComponent(DiscReviewWidget, {
				props: { job: createJob({ status: 'awaiting_review' }), driveNames: {}, paused: false, ondismiss }
			});
			await fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));
			expect(await screen.findByText('409 job cannot be abandoned')).toBeInTheDocument();
			expect(ondismiss).not.toHaveBeenCalled();
		});
	});

	describe('sections', () => {
		it('opens the Info section (replaces the removed Disc info panel)', async () => {
			renderWidget();
			// Info is now the first action button; the old "Disc info" panel is gone
			// (disc number/total moved into the Info form).
			await waitFor(() => expect(screen.getByText('Info')).toBeInTheDocument());
			expect(screen.queryByText('Disc info')).not.toBeInTheDocument();
			await fireEvent.click(screen.getByText('Info'));
			await waitFor(() => {
				expect(screen.getByLabelText('Title')).toBeInTheDocument();
			});
		});
	});

	describe('guest write-control gating', () => {
		afterEach(async () => {
			const auth = (await import('$lib/stores/auth')) as unknown as {
				__setRole: (r: string | null) => void;
			};
			auth.__setRole('admin');
		});

		it('hides Start rip, Apply session, Cancel for guests but keeps Info and View details', async () => {
			const auth = (await import('$lib/stores/auth')) as unknown as {
				__setRole: (r: string | null) => void;
			};
			auth.__setRole('guest');
			renderWidget({ status: 'awaiting_review' });
			await waitFor(() => expect(screen.getByText('Info')).toBeInTheDocument());
			expect(screen.queryByText('Start rip')).not.toBeInTheDocument();
			expect(screen.queryByText(/Apply session/)).not.toBeInTheDocument();
			expect(screen.queryByText('Cancel')).not.toBeInTheDocument();
			expect(screen.getByText('View details')).toBeInTheDocument();
		});

		it('shows Start rip and Cancel for admins (Apply session follows job.actions.can_apply)', async () => {
			renderWidget({ status: 'awaiting_review' });
			await waitFor(() => expect(screen.getByText('Start rip')).toBeInTheDocument());
			expect(screen.getByText('Cancel')).toBeInTheDocument();
			expect(screen.getByText(/Apply session/)).toBeInTheDocument();
		});
	});

	describe('ISO rip', () => {
		it('shows the ISO chip instead of the drive pill for an ISO rip', async () => {
			renderWidget({ status: 'awaiting_review', drive_id: 'drv_iso_1' }, { drv_iso_1: 'Paddington_2.iso' });
			await waitFor(() => expect(screen.getByText('Start rip')).toBeInTheDocument());
			expect(screen.getByText('ISO')).toBeInTheDocument();
			expect(screen.getAllByText('Paddington_2.iso').length).toBeGreaterThan(0);
			expect(screen.queryByText('drv_iso_1')).not.toBeInTheDocument();
		});

		it('keeps the drive pill for a physical-drive rip', async () => {
			renderWidget({ status: 'awaiting_review', drive_id: 'drv_1' }, null);
			await waitFor(() => expect(screen.getByText('Start rip')).toBeInTheDocument());
			expect(screen.queryByText('ISO')).not.toBeInTheDocument();
			expect(screen.getByText('drv_1')).toBeInTheDocument();
		});

		it('marks the card root data-source="iso" for an ISO rip', async () => {
			const { container } = renderWidget({ status: 'awaiting_review', drive_id: 'drv_iso_1' }, { drv_iso_1: 'a.iso' });
			await waitFor(() => expect(screen.getByText('Start rip')).toBeInTheDocument());
			expect(container.querySelector('.disc-review-widget')).toHaveAttribute('data-source', 'iso');
		});

		it('titles Cancel for an ISO rip and cancels through cancelIsoRip', async () => {
			const { cancelIsoRip } = await import('$lib/api/iso');
			renderWidget({ status: 'awaiting_review', drive_id: 'drv_iso_1' }, { drv_iso_1: 'a.iso' });
			await waitFor(() => expect(screen.getByText('Cancel')).toBeInTheDocument());
			const cancelBtn = screen.getByText('Cancel');
			expect(cancelBtn).toHaveAttribute('title', 'Cancel the rip and remove the virtual drive');
			await fireEvent.click(cancelBtn);
			await waitFor(() => expect(cancelIsoRip).toHaveBeenCalledWith('drv_iso_1'));
			const { abandonJob } = await import('$lib/api/jobs');
			expect(abandonJob).not.toHaveBeenCalled();
		});
	});

	describe('already ripped (D-132)', () => {
		const held = createJob({
			status: 'awaiting_review',
			title: 'Resident Evil: Retribution',
			wait_start_time: null,
			metadata_json: { previously_ripped: { job_id: 'job_old' } } as never
		});
		const previous = {
			job_id: 'job_old',
			title: 'Resident Evil: Retribution',
			year: 2012,
			status: 'ripped' as const,
			ripped_at: '2026-10-12T06:35:00Z',
			outputs_present: true
		};

		async function renderHeld(previousRip: typeof previous | null) {
			const { fetchJob } = await import('$lib/api/jobs');
			const original = vi.mocked(fetchJob).getMockImplementation();
			vi.mocked(fetchJob).mockResolvedValue({ ...createJobDetail(), job: held, previous_rip: previousRip });
			const ondismiss = vi.fn();
			renderComponent(DiscReviewWidget, { props: { job: held, driveNames: {}, paused: false, ondismiss } });
			return { ondismiss, restore: () => vi.mocked(fetchJob).mockImplementation(original!) };
		}

		it('names the earlier rip and offers Rip again or Discard', async () => {
			const { restore } = await renderHeld(previous);
			try {
				expect(await screen.findByText('Already ripped: Rip again or Discard')).toBeInTheDocument();
				expect(screen.getByText('ALREADY RIPPED')).toBeInTheDocument();
				const link = await screen.findByRole('link', { name: 'Resident Evil: Retribution' });
				expect(link).toHaveAttribute('href', '/jobs/job_old');
				expect(screen.getByText('Its files are still in the library.')).toBeInTheDocument();
				expect(screen.getByRole('button', { name: 'Rip again' })).toBeInTheDocument();
				expect(screen.getByRole('button', { name: 'Discard' })).toBeInTheDocument();
				expect(screen.queryByRole('button', { name: 'Start rip' })).toBeNull();
			} finally {
				restore();
			}
		});

		it('Rip again starts the held disc', async () => {
			const { startWaitingJob } = await import('$lib/api/jobs');
			const { ondismiss, restore } = await renderHeld(previous);
			try {
				await fireEvent.click(await screen.findByRole('button', { name: 'Rip again' }));
				await waitFor(() => expect(startWaitingJob).toHaveBeenCalledWith('job_1'));
				await waitFor(() => expect(ondismiss).toHaveBeenCalled());
			} finally {
				restore();
			}
		});

		it('says so when the earlier job has since been deleted', async () => {
			const { restore } = await renderHeld(null);
			try {
				expect(
					await screen.findByText('ARM ripped this disc before, but that job has since been deleted.')
				).toBeInTheDocument();
			} finally {
				restore();
			}
		});
	});

	describe('held identity suggestion', () => {
		const suggestionMeta = {
			identity_suggestion: {
				provider: 'tmdb',
				title: 'Iron Man',
				year: 2008,
				kind: 'movie',
				poster_url: 'https://image.tmdb.org/t/p/w500/abc.jpg',
				external_ids: {},
				overview: null,
				payload: {},
				suggested_at: '2026-10-15T10:00:00Z'
			},
			flags: { unidentified: true }
		};
		const heldFor = (disc_type: 'bluray' | 'cd' = 'bluray', extraMeta: Record<string, unknown> = {}) =>
			createJob({
				status: 'awaiting_review',
				title: 'MY_DISC',
				disc_type,
				wait_start_time: null,
				metadata_json: { ...suggestionMeta, ...extraMeta } as never
			});

		async function renderSuggested(disc_type: 'bluray' | 'cd' = 'bluray', extraMeta: Record<string, unknown> = {}) {
			const held = heldFor(disc_type, extraMeta);
			const { fetchJob } = await import('$lib/api/jobs');
			const original = vi.mocked(fetchJob).getMockImplementation();
			vi.mocked(fetchJob).mockResolvedValue({ ...createJobDetail(), job: held });
			const onrefresh = vi.fn();
			renderComponent(DiscReviewWidget, { props: { job: held, driveNames: {}, paused: false, onrefresh } });
			return { onrefresh, restore: () => vi.mocked(fetchJob).mockImplementation(original!) };
		}

		it('asks to confirm the title, shows the banner, keeps Start rip', async () => {
			const { restore } = await renderSuggested();
			try {
				expect(await screen.findByText('Confirm the title: use it or search')).toBeInTheDocument();
				expect(screen.getByText('CONFIRM TITLE')).toBeInTheDocument();
				expect(screen.getByTestId('identity-suggestion')).toBeInTheDocument();
				expect(screen.getByText('Iron Man (2008)')).toBeInTheDocument();
				expect(screen.getByRole('button', { name: 'Start rip' })).toBeInTheDocument();
			} finally {
				restore();
			}
		});

		it('Use this title accepts, reloads the detail and refreshes the parent', async () => {
			const { acceptIdentitySuggestion, fetchJob } = await import('$lib/api/jobs');
			const { onrefresh, restore } = await renderSuggested();
			try {
				await waitFor(() => expect(fetchJob).toHaveBeenCalledTimes(1));
				await fireEvent.click(await screen.findByRole('button', { name: 'Use this title' }));
				await waitFor(() => expect(acceptIdentitySuggestion).toHaveBeenCalledWith('job_1'));
				await waitFor(() => expect(onrefresh).toHaveBeenCalled());
				await waitFor(() => expect(fetchJob).toHaveBeenCalledTimes(2));
			} finally {
				restore();
			}
		});

		it('Search instead opens the title search for a video disc', async () => {
			const { restore } = await renderSuggested();
			try {
				expect(screen.queryByPlaceholderText('Title...')).toBeNull();
				await fireEvent.click(await screen.findByRole('button', { name: 'Search instead' }));
				expect(await screen.findByPlaceholderText('Title...')).toBeInTheDocument();
			} finally {
				restore();
			}
		});

		it('Search instead opens the music search for a CD', async () => {
			const { restore } = await renderSuggested('cd');
			try {
				expect(screen.queryByPlaceholderText('Album or title...')).toBeNull();
				await fireEvent.click(await screen.findByRole('button', { name: 'Search instead' }));
				expect(await screen.findByPlaceholderText('Album or title...')).toBeInTheDocument();
			} finally {
				restore();
			}
		});

		it('on a previously-ripped hold, keeps the hold label and badge and still offers the banner', async () => {
			const { acceptIdentitySuggestion } = await import('$lib/api/jobs');
			const { onrefresh, restore } = await renderSuggested('bluray', { previously_ripped: { job_id: 'job_old' } });
			try {
				expect(await screen.findByText('Already ripped: Rip again or Discard')).toBeInTheDocument();
				expect(screen.getByText('ALREADY RIPPED')).toBeInTheDocument();
				expect(screen.queryByText('CONFIRM TITLE')).toBeNull();
				expect(screen.getByTestId('identity-suggestion')).toBeInTheDocument();
				await fireEvent.click(screen.getByRole('button', { name: 'Use this title' }));
				await waitFor(() => expect(acceptIdentitySuggestion).toHaveBeenCalledWith('job_1'));
				await waitFor(() => expect(onrefresh).toHaveBeenCalled());
			} finally {
				restore();
			}
		});

		it('a guest sees the banner without its buttons', async () => {
			const auth = (await import('$lib/stores/auth')) as unknown as { __setRole: (r: string | null) => void };
			auth.__setRole('guest');
			const { restore } = await renderSuggested();
			try {
				expect(await screen.findByTestId('identity-suggestion')).toBeInTheDocument();
				expect(screen.queryByRole('button', { name: 'Use this title' })).toBeNull();
				expect(screen.queryByRole('button', { name: 'Search instead' })).toBeNull();
			} finally {
				auth.__setRole('admin');
				restore();
			}
		});
	});

	describe('footer wrap', () => {
		it('wraps the footer actions', async () => {
			const { container } = renderWidget({ status: 'awaiting_review' });
			await waitFor(() => expect(screen.getByText('Start rip')).toBeInTheDocument());
			expect(container.querySelector('.disc-review-widget-actions')).toHaveClass('flex-wrap');
		});
	});
});
