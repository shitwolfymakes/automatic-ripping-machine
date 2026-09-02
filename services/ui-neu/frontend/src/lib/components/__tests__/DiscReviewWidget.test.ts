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
	startWaitingJob: vi.fn(() => Promise.resolve(createJob())),
	updateTrack: vi.fn(() => Promise.resolve(createJob())),
	updateJobTitle: vi.fn(() => Promise.resolve(createJob())),
	updateJobConfig: vi.fn(() => Promise.resolve(createJob())),
	updateJobNaming: vi.fn(() => Promise.reject(new Error('not available'))),
	updateJobTranscodeConfig: vi.fn(() => Promise.reject(new Error('not available'))),
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
	fetchTranscoderScheme: vi.fn(() => Promise.resolve(null)),
	fetchTranscoderPresets: vi.fn(() => Promise.resolve(null))
}));

vi.mock('$lib/api/sessions', () => ({
	fetchSessions: vi.fn(() => Promise.resolve([]))
}));

function renderWidget(overrides = {}) {
	return renderComponent(DiscReviewWidget, {
		props: { job: createJob({ status: 'identified', ...overrides }), driveNames: {}, paused: false }
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

		it('shows Start rip, Apply session, Cancel for admins', async () => {
			renderWidget({ status: 'awaiting_review' });
			await waitFor(() => expect(screen.getByText('Start rip')).toBeInTheDocument());
			expect(screen.getByText(/Apply session/)).toBeInTheDocument();
			expect(screen.getByText('Cancel')).toBeInTheDocument();
		});
	});
});
