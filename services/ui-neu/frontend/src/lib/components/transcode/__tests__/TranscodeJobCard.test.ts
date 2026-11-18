import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { mount, unmount } from 'svelte';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/testing/render';
import type { TranscodeTaskView } from '$lib/types/api.gen';
import TranscodeJobCard from '../TranscodeJobCard.svelte';

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

async function setRole(r: string | null) {
	const auth = (await import('$lib/stores/auth')) as unknown as {
		__setRole: (r: string | null) => void;
	};
	auth.__setRole(r);
}

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

function renderCard(job: TranscodeTaskView) {
	const onretry = vi.fn();
	const ondelete = vi.fn();
	const view = renderComponent(TranscodeJobCard, { props: { job, onretry, ondelete } });
	return { ...view, onretry, ondelete };
}

function timestamps(container: HTMLElement): string {
	return container.querySelector('div.transcoder-page-job-meta-sm')?.textContent ?? '';
}

beforeEach(async () => {
	vi.useFakeTimers({ toFake: ['Date'] });
	vi.setSystemTime(new Date('2025-06-15T12:00:00Z'));
	await setRole('admin');
});

afterEach(() => {
	cleanup();
	vi.useRealTimers();
});

describe('TranscodeJobCard title', () => {
	it('shows the output path basename with the full path as its title', () => {
		renderCard(makeTask());
		const h3 = screen.getByText('movie1.mkv', { selector: 'h3' });
		expect(h3).toHaveAttribute('title', '/media/transcode/movie1.mkv');
	});

	it('falls back to Task #id titled by the source track when there is no output path', () => {
		renderCard(makeTask({ output_path: null }));
		const h3 = screen.getByText('Task #t-1', { selector: 'h3' });
		expect(h3).toHaveAttribute('title', 'track-1');
	});
});

describe('TranscodeJobCard admin actions', () => {
	it('shows Retry only on a failed task and calls onretry with the id', async () => {
		const { onretry } = renderCard(makeTask({ status: 'failed' }));
		await fireEvent.click(screen.getByText('Retry'));
		expect(onretry).toHaveBeenCalledWith('t-1');
	});

	it('shows no Retry on a task that has not failed', () => {
		renderCard(makeTask({ status: 'done' }));
		expect(screen.queryByText('Retry')).not.toBeInTheDocument();
	});

	it('shows Delete on every task and calls ondelete with the id', async () => {
		const { ondelete } = renderCard(makeTask({ status: 'done' }));
		await fireEvent.click(screen.getByText('Delete'));
		expect(ondelete).toHaveBeenCalledWith('t-1');
	});

	it('shows no buttons to a non-admin', async () => {
		await setRole('guest');
		renderCard(makeTask({ status: 'failed' }));
		expect(screen.queryByText('Retry')).not.toBeInTheDocument();
		expect(screen.queryByText('Delete')).not.toBeInTheDocument();
	});
});

describe('TranscodeJobCard meta row', () => {
	it('links to the job when job_id is set', () => {
		renderCard(makeTask());
		const link = screen.getByTestId('transcode-job-link');
		expect(link).toHaveAttribute('href', '/jobs/job_abc');
		expect(link).toHaveTextContent('Job job_abc');
		expect(screen.queryByText('No job')).not.toBeInTheDocument();
	});

	it('shows the No job chip when job_id is null', () => {
		renderCard(makeTask({ job_id: null }));
		expect(screen.getByText('No job')).toBeInTheDocument();
		expect(screen.queryByTestId('transcode-job-link')).not.toBeInTheDocument();
	});

	it('shows the attempt count above zero', () => {
		renderCard(makeTask({ attempts: 3 }));
		expect(screen.getByText('Attempt 3')).toBeInTheDocument();
	});

	it('shows no attempt count at zero', () => {
		renderCard(makeTask({ attempts: 0 }));
		expect(screen.queryByText(/Attempt/)).not.toBeInTheDocument();
	});

	it('shows claimed_by when set', () => {
		renderCard(makeTask({ claimed_by: 'gpu-0' }));
		expect(screen.getByText('gpu-0')).toBeInTheDocument();
	});

	it('shows no claimant when claimed_by is null', () => {
		const { container } = renderCard(makeTask({ claimed_by: null }));
		expect(container.querySelector('.transcoder-page-claimed-by')).toBeNull();
	});
});

describe('TranscodeJobCard error and progress', () => {
	it('shows last_error on a failed task', () => {
		renderCard(makeTask({ status: 'failed', last_error: 'boom' }));
		expect(screen.getByText('boom')).toBeInTheDocument();
	});

	it('hides last_error on a done task that has one', () => {
		renderCard(makeTask({ status: 'done', last_error: 'old failure' }));
		expect(screen.queryByText('old failure')).not.toBeInTheDocument();
	});

	it.each(['queued', 'in_progress'] as const)('shows the progress bar on a %s task', (status) => {
		const { container } = renderCard(makeTask({ status, progress_pct: 40 }));
		expect(container.querySelector('[data-progress-track]')).toBeInTheDocument();
	});

	it('shows no progress bar on a done task', () => {
		const { container } = renderCard(makeTask({ status: 'done' }));
		expect(container.querySelector('[data-progress-track]')).toBeNull();
	});
});

describe('TranscodeJobCard timestamps', () => {
	it('shows Queued and Updated when both stamps are set', () => {
		const { container } = renderCard(makeTask());
		expect(timestamps(container)).toContain('Queued');
		expect(timestamps(container)).toContain('Updated');
	});

	it('shows no Queued when created_at is null', () => {
		const { container } = renderCard(makeTask({ created_at: null }));
		expect(timestamps(container)).not.toContain('Queued');
		expect(timestamps(container)).toContain('Updated');
	});

	it('shows no Updated when updated_at is null', () => {
		const { container } = renderCard(makeTask({ updated_at: null }));
		expect(timestamps(container)).toContain('Queued');
		expect(timestamps(container)).not.toContain('Updated');
	});
});

describe('TranscodeJobCard duration', () => {
	it('shows Took from started_at on a done task', () => {
		const { container } = renderCard(makeTask({ status: 'done', started_at: '2025-06-15T10:01:00Z' }));
		expect(timestamps(container)).toContain('Took 4m 0s');
	});

	it('falls back to created_at when started_at is missing', () => {
		const { container } = renderCard(makeTask({ status: 'done', started_at: null }));
		expect(timestamps(container)).toContain('Took 5m 0s');
	});

	it('shows no Took when there is no start stamp', () => {
		const { container } = renderCard(makeTask({ status: 'done', started_at: null, created_at: null }));
		expect(timestamps(container)).not.toContain('Took');
	});

	it('shows no Took when there is no updated_at', () => {
		const { container } = renderCard(makeTask({ status: 'done', updated_at: null }));
		expect(timestamps(container)).not.toContain('Took');
	});

	it('shows no Took when the stamps are unparsable', () => {
		const { container } = renderCard(makeTask({ status: 'done', started_at: 'garbage' }));
		expect(timestamps(container)).not.toContain('Took');
	});

	it('shows no Took on a task that is not done', () => {
		const { container } = renderCard(makeTask({ status: 'in_progress', started_at: '2025-06-15T10:01:00Z' }));
		expect(timestamps(container)).not.toContain('Took');
	});
});

describe('TranscodeJobCard output path', () => {
	it('shows the output path line on a done task with an output path', () => {
		const { container } = renderCard(makeTask({ status: 'done' }));
		const line = container.querySelector('span.mono.truncate');
		expect(line).toHaveTextContent('movie1.mkv');
		expect(line).toHaveAttribute('title', '/media/transcode/movie1.mkv');
		expect(container.querySelector('.transcoder-page-arrow')).toBeInTheDocument();
	});

	it('shows no output path line on a done task without one', () => {
		const { container } = renderCard(makeTask({ status: 'done', output_path: null }));
		expect(container.querySelector('.transcoder-page-arrow')).toBeNull();
	});

	it('shows no output path line on a failed task with one', () => {
		const { container } = renderCard(makeTask({ status: 'failed' }));
		expect(container.querySelector('.transcoder-page-arrow')).toBeNull();
	});
});

describe('TranscodeJobCard transition', () => {
	it('fades out when it is unmounted with an outro', async () => {
		const target = document.createElement('div');
		document.body.appendChild(target);
		const component = mount(TranscodeJobCard, {
			target,
			props: { job: makeTask(), onretry: vi.fn(), ondelete: vi.fn() }
		});
		await unmount(component, { outro: true });
		expect(target.textContent).toBe('');
		target.remove();
	});
});
