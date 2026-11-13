// The review card's action buttons, rendered with a real ReviewSections and a
// real DiscReviewJobActions whose callbacks and API calls are faked.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { tick } from 'svelte';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import type { JobView } from '$lib/types/api.gen';
import type { EpisodeState, EpisodeStatus } from '$lib/episodes/status';
import { ReviewSections } from '$lib/stores/review-sections.svelte';
import { DiscReviewJobActions } from '$lib/stores/disc-review-job-actions.svelte';
import { actionsFor, createJob } from '../../__fixtures__/job';
import DiscReviewActions from '../DiscReviewActions.svelte';

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		// Test-only helper, not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});

vi.mock('$lib/api/jobs', () => ({
	abandonJob: vi.fn(),
	deleteJob: vi.fn(),
	startWaitingJob: vi.fn(),
	pauseWaitingJob: vi.fn(),
	resolveJob: vi.fn()
}));
vi.mock('$lib/api/iso', () => ({ cancelIsoRip: vi.fn() }));

async function setRole(role: string | null) {
	const auth = (await import('$lib/stores/auth')) as unknown as { __setRole: (r: string | null) => void };
	auth.__setRole(role);
}

interface Options {
	job?: JobView;
	isVideo?: boolean;
	isMusic?: boolean;
	isPostRip?: boolean;
	canStart?: boolean;
	episodeRow?: EpisodeStatus | null;
	previouslyRipped?: boolean;
	fromIso?: boolean;
}

function row(state: EpisodeState): EpisodeStatus {
	return { state, source: null, total: null, unmatched: null };
}

// A job whose status offers every admin action at once.
function jobWith(flags: Partial<JobView['actions']>): JobView {
	return createJob({
		actions: { can_resolve: false, can_apply: false, can_abandon: false, can_delete: false, ...flags }
	});
}

function setup(options: Options = {}) {
	const sections = new ReviewSections();
	const actions = new DiscReviewJobActions({ dismiss: vi.fn(), refresh: vi.fn() });
	const onapplysession = vi.fn();
	const oncancel = vi.fn();
	const onstartrip = vi.fn();
	renderComponent(DiscReviewActions, {
		job: options.job ?? createJob({ id: 'job_7', actions: actionsFor('ripping') }),
		sections,
		actions,
		isVideo: options.isVideo ?? false,
		isMusic: options.isMusic ?? false,
		isPostRip: options.isPostRip ?? false,
		canStart: options.canStart ?? false,
		episodeRow: options.episodeRow ?? null,
		previouslyRipped: options.previouslyRipped ?? false,
		fromIso: options.fromIso ?? false,
		onapplysession,
		oncancel,
		onstartrip
	});
	return { sections, actions, onapplysession, oncancel, onstartrip };
}

const btn = (name: string) => screen.getByRole('button', { name });
const maybeBtn = (name: string) => screen.queryByRole('button', { name });

beforeEach(async () => {
	await setRole('admin');
});

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe('DiscReviewActions: Info', () => {
	it('toggles the info section, and aria-pressed follows it', async () => {
		const { sections } = setup();
		expect(btn('Info')).toHaveAttribute('aria-pressed', 'false');
		await fireEvent.click(btn('Info'));
		expect(sections.isOpen('info')).toBe(true);
		await waitFor(() => expect(btn('Info')).toHaveAttribute('aria-pressed', 'true'));
		await fireEvent.click(btn('Info'));
		expect(sections.isOpen('info')).toBe(false);
	});
});

describe('DiscReviewActions: Search', () => {
	it('toggles the title section for a video disc', async () => {
		const { sections } = setup({ isVideo: true });
		await fireEvent.click(btn('Search'));
		expect(sections.isOpen('title')).toBe(true);
		await waitFor(() => expect(btn('Search')).toHaveAttribute('aria-pressed', 'true'));
	});

	it('toggles the music section for a music disc', async () => {
		const { sections } = setup({ isMusic: true });
		await fireEvent.click(btn('Search'));
		expect(sections.isOpen('music')).toBe(true);
		await waitFor(() => expect(btn('Search')).toHaveAttribute('aria-pressed', 'true'));
	});

	it('shows no Search for a data disc', () => {
		setup();
		expect(maybeBtn('Search')).toBeNull();
	});
});

describe('DiscReviewActions: Episodes', () => {
	it('is hidden for a null row', () => {
		setup({ episodeRow: null });
		expect(maybeBtn('Episodes')).toBeNull();
	});

	it('is hidden for a matched row while the section is closed', () => {
		setup({ episodeRow: row('matched') });
		expect(maybeBtn('Episodes')).toBeNull();
	});

	it('is shown for a matched row while the section is open', async () => {
		const { sections } = setup({ episodeRow: row('matched') });
		sections.open('episodes');
		await tick();
		expect(btn('Episodes')).toHaveAttribute('aria-pressed', 'true');
	});

	it.each(['waiting', 'matching', 'guess', 'attention'] as EpisodeState[])('is shown for a %s row', (state) => {
		setup({ episodeRow: row(state) });
		expect(btn('Episodes')).toBeInTheDocument();
	});

	it('toggles the episodes section', async () => {
		const { sections } = setup({ episodeRow: row('attention') });
		await fireEvent.click(btn('Episodes'));
		expect(sections.isOpen('episodes')).toBe(true);
	});
});

describe('DiscReviewActions: Apply session', () => {
	it('is shown to an admin when the job can be applied', () => {
		setup({ job: jobWith({ can_apply: true }) });
		expect(btn('Apply session')).toBeInTheDocument();
	});

	it('is hidden when the job cannot be applied', () => {
		setup({ job: jobWith({}) });
		expect(maybeBtn('Apply session')).toBeNull();
	});

	it('uses the action class before the rip is done', () => {
		setup({ job: jobWith({ can_apply: true }) });
		expect(btn('Apply session')).toHaveClass('disc-review-widget-action-btn');
	});

	it('reads "Apply session & transcode" with the success class post-rip', () => {
		setup({ job: jobWith({ can_apply: true }), isPostRip: true });
		const button = btn('Apply session & transcode');
		expect(button).toHaveClass('disc-review-widget-success-btn');
		expect(button).not.toHaveClass('disc-review-widget-action-btn');
	});

	it('calls onapplysession', async () => {
		const { onapplysession } = setup({ job: jobWith({ can_apply: true }) });
		await fireEvent.click(btn('Apply session'));
		expect(onapplysession).toHaveBeenCalledTimes(1);
	});
});

describe('DiscReviewActions: View details', () => {
	it('links to the job page', () => {
		setup();
		expect(screen.getByRole('link', { name: 'View details' })).toHaveAttribute('href', '/jobs/job_7');
	});
});

describe('DiscReviewActions: Cancel', () => {
	it('is shown to an admin when the job can be abandoned', () => {
		setup({ job: jobWith({ can_abandon: true }) });
		expect(btn('Cancel')).toBeInTheDocument();
	});

	it('is hidden when the job cannot be abandoned', () => {
		setup({ job: jobWith({}) });
		expect(maybeBtn('Cancel')).toBeNull();
	});

	it('reads "Cancelling..." and is disabled while cancelling', async () => {
		const { actions } = setup({ job: jobWith({ can_abandon: true }) });
		actions.cancelling = true;
		await tick();
		expect(btn('Cancelling...')).toBeDisabled();
	});

	it('reads "Discard" for a previously ripped disc', () => {
		setup({ job: jobWith({ can_abandon: true }), previouslyRipped: true });
		expect(btn('Discard')).toBeInTheDocument();
		expect(maybeBtn('Cancel')).toBeNull();
	});

	it('carries the ISO title when the disc is an ISO rip', () => {
		setup({ job: jobWith({ can_abandon: true }), fromIso: true });
		expect(btn('Cancel')).toHaveAttribute('title', 'Cancel the rip and remove the virtual drive');
	});

	it('has no title when the disc is not an ISO rip', () => {
		setup({ job: jobWith({ can_abandon: true }) });
		expect(btn('Cancel')).not.toHaveAttribute('title');
	});

	it('calls oncancel', async () => {
		const { oncancel } = setup({ job: jobWith({ can_abandon: true }) });
		await fireEvent.click(btn('Cancel'));
		expect(oncancel).toHaveBeenCalledTimes(1);
	});
});

describe('DiscReviewActions: Delete', () => {
	it('is shown to an admin when the job can be deleted', () => {
		setup({ job: jobWith({ can_delete: true }) });
		expect(btn('Delete')).toBeInTheDocument();
	});

	it('is hidden when the job cannot be deleted', () => {
		setup({ job: jobWith({}) });
		expect(maybeBtn('Delete')).toBeNull();
	});

	it('asks for the delete confirmation', async () => {
		const { actions } = setup({ job: jobWith({ can_delete: true }) });
		await fireEvent.click(btn('Delete'));
		expect(actions.confirmDelete).toBe(true);
	});

	it('reads "Deleting..." and is disabled while deleting', async () => {
		const { actions } = setup({ job: jobWith({ can_delete: true }) });
		actions.deleting = true;
		await tick();
		expect(btn('Deleting...')).toBeDisabled();
	});
});

describe('DiscReviewActions: Start rip', () => {
	it('is hidden when the rip cannot be started', () => {
		setup({ canStart: false });
		expect(maybeBtn('Start rip')).toBeNull();
	});

	it('reads "Start rip" with its title, and calls onstartrip', async () => {
		const { onstartrip } = setup({ canStart: true });
		const button = btn('Start rip');
		expect(button).toHaveAttribute('title', 'Save the metadata and start ripping this disc');
		await fireEvent.click(button);
		expect(onstartrip).toHaveBeenCalledTimes(1);
	});

	it('reads "Rip again" with its title for a previously ripped disc', () => {
		setup({ canStart: true, previouslyRipped: true });
		expect(btn('Rip again')).toHaveAttribute('title', 'Rip this disc again');
	});

	it('reads "Starting..." and is disabled while starting', async () => {
		const { actions } = setup({ canStart: true });
		actions.starting = true;
		await tick();
		expect(btn('Starting...')).toBeDisabled();
	});
});

describe('DiscReviewActions: a non-admin', () => {
	it('sees none of the admin buttons', async () => {
		await setRole('viewer');
		setup({
			job: jobWith({ can_apply: true, can_abandon: true, can_delete: true }),
			canStart: true
		});
		expect(maybeBtn('Apply session')).toBeNull();
		expect(maybeBtn('Cancel')).toBeNull();
		expect(maybeBtn('Delete')).toBeNull();
		expect(maybeBtn('Start rip')).toBeNull();
		expect(btn('Info')).toBeInTheDocument();
	});
});
