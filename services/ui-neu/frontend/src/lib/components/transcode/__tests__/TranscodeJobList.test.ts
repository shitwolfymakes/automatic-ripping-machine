import { describe, it, expect, afterEach, vi } from 'vitest';
import type { ComponentProps } from 'svelte';
import { renderComponent, screen, fireEvent, waitFor, cleanup } from '$lib/testing/render';
import type { TranscodeTaskView } from '$lib/types/api.gen';
import TranscodeJobList from '../TranscodeJobList.svelte';

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

// jsdom cannot run Web Animations, so an outro would never finish; a
// transition with no duration finishes synchronously.
vi.mock('svelte/transition', () => ({
	fade: () => ({ duration: 0 })
}));

function makeTask(overrides: Partial<TranscodeTaskView> = {}): TranscodeTaskView {
	return {
		id: 't-1',
		session_application_id: 'sap_1',
		job_id: 'job_abc',
		source_track_id: 'track-1',
		status: 'queued',
		output_path: '/media/transcode/movie1.mkv',
		progress_pct: 0,
		attempts: 0,
		claimed_by: null,
		claim_heartbeat_at: null,
		last_error: null,
		created_at: '2025-06-15T10:00:00Z',
		updated_at: '2025-06-15T10:05:00Z',
		...overrides
	} as TranscodeTaskView;
}

function renderList(props: Partial<ComponentProps<typeof TranscodeJobList>> = {}) {
	const onretry = vi.fn();
	const ondelete = vi.fn();
	const view = renderComponent(TranscodeJobList, {
		props: { jobs: [], loading: false, error: null, totalTasks: 0, onretry, ondelete, ...props }
	});
	return { ...view, onretry, ondelete };
}

// LoadState reserves the skeleton hidden for 150 ms, then reveals it.
async function skeletonCards(container: HTMLElement): Promise<number> {
	await waitFor(() => expect(container.querySelector('[data-phase="waiting"]')).toBeNull());
	return container.querySelectorAll('[aria-busy="true"]').length;
}

afterEach(() => {
	cleanup();
});

describe('TranscodeJobList loading', () => {
	it.each([
		[0, 3],
		[4, 4],
		[10, 6]
	])('shows placeholders for %i total tasks as %i skeleton cards', async (totalTasks, cards) => {
		const { container } = renderList({ loading: true, totalTasks });
		expect(await skeletonCards(container)).toBe(cards);
	});
});

describe('TranscodeJobList states', () => {
	it('shows the empty text for an empty list', () => {
		renderList();
		expect(screen.getByText('No transcode tasks found.')).toBeInTheDocument();
	});

	it('shows the error message for an Error', () => {
		renderList({ error: new Error('boom') });
		expect(screen.getByText('Failed to load: boom')).toBeInTheDocument();
	});

	it('renders one card per task in the order given', () => {
		renderList({
			jobs: [makeTask({ id: 't-2', output_path: '/m/b.mkv' }), makeTask({ id: 't-1', output_path: '/m/a.mkv' })]
		});
		const titles = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent?.trim());
		expect(titles).toEqual(['b.mkv', 'a.mkv']);
	});
});

describe('TranscodeJobList actions', () => {
	it('calls onretry with the id of a failed task', async () => {
		const { onretry } = renderList({ jobs: [makeTask({ id: 't-9', status: 'failed' })] });
		await fireEvent.click(screen.getByText('Retry'));
		expect(onretry).toHaveBeenCalledWith('t-9');
	});

	it('calls ondelete with the id of a task', async () => {
		const { ondelete } = renderList({ jobs: [makeTask({ id: 't-7' })] });
		await fireEvent.click(screen.getByText('Delete'));
		expect(ondelete).toHaveBeenCalledWith('t-7');
	});
});
