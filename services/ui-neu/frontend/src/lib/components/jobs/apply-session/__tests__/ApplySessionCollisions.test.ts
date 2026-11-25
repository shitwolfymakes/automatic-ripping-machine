import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/testing/render';
import ApplySessionCollisions from '../ApplySessionCollisions.svelte';
import type { CollisionInfo } from '$lib/types/api.gen';

const JOB_ID = 'job-applying-0001';
const OTHER_JOB_ID = 'job-someone-else-12345678';

function collision(over: Partial<CollisionInfo> = {}): CollisionInfo {
	return {
		output_path: '/out/a.mkv',
		existing_task_id: null,
		on_filesystem: false,
		reason: 'existing_task',
		existing_job_id: null,
		...over
	};
}

function renderView(collisions: CollisionInfo[], over: Record<string, unknown> = {}) {
	const onclose = vi.fn();
	const onoverwrite = vi.fn();
	renderComponent(ApplySessionCollisions, {
		props: { collisions, jobId: JOB_ID, submitting: false, onclose, onoverwrite, ...over }
	});
	return { onclose, onoverwrite };
}

afterEach(() => {
	cleanup();
});

describe('ApplySessionCollisions', () => {
	it('renders one row per collision with its path in a code element', () => {
		renderView([collision({ output_path: '/out/a.mkv' }), collision({ output_path: '/out/b.mkv' })]);
		expect(screen.getByText('/out/a.mkv').tagName).toBe('CODE');
		expect(screen.getByText('/out/b.mkv').tagName).toBe('CODE');
		expect(screen.getAllByRole('listitem')).toHaveLength(2);
	});

	it.each([
		['existing_task', '(queued/done in DB)'],
		['on_disk', '(exists on disk)'],
		['duplicate_in_request', '(duplicate within this apply)']
	] as const)('labels a %s collision', (reason, text) => {
		renderView([collision({ reason })]);
		expect(screen.getByText(text)).toBeTruthy();
	});

	it('adds no owner suffix when the owner is unknown', () => {
		renderView([collision({ existing_job_id: null })]);
		expect(screen.getByText('(queued/done in DB)')).toBeTruthy();
	});

	it('adds no owner suffix when the applying job owns the collision', () => {
		renderView([collision({ existing_job_id: JOB_ID })]);
		expect(screen.getByText('(queued/done in DB)')).toBeTruthy();
	});

	it("names the last 8 characters of another job's id", () => {
		renderView([collision({ existing_job_id: OTHER_JOB_ID })]);
		expect(screen.getByText('(queued/done in DB in job 12345678)')).toBeTruthy();
	});

	it('shows the cross-job notice without Overwrite, even beside a duplicate', () => {
		renderView([collision({ reason: 'duplicate_in_request' }), collision({ existing_job_id: OTHER_JOB_ID })]);
		expect(screen.getByTestId('cross-job-collision-notice')).toBeTruthy();
		expect(screen.queryByTestId('apply-session-overwrite')).toBeNull();
		expect(screen.queryByText(/won't help here/)).toBeNull();
	});

	it('shows the duplicate note without Overwrite', () => {
		renderView([collision({ reason: 'duplicate_in_request' })]);
		expect(screen.getByText(/won't help here/)).toBeTruthy();
		expect(screen.queryByTestId('cross-job-collision-notice')).toBeNull();
		expect(screen.queryByTestId('apply-session-overwrite')).toBeNull();
	});

	it('shows the confirm note with Overwrite otherwise', () => {
		renderView([collision({ existing_job_id: JOB_ID })]);
		expect(screen.getByText(/to queue anyway/)).toBeTruthy();
		expect(screen.queryByTestId('cross-job-collision-notice')).toBeNull();
		expect(screen.getByTestId('apply-session-overwrite').textContent?.trim()).toBe('Overwrite');
	});

	it('disables Overwrite and reads Applying... while submitting', () => {
		renderView([collision()], { submitting: true });
		const btn = screen.getByTestId('apply-session-overwrite') as HTMLButtonElement;
		expect(btn.disabled).toBe(true);
		expect(btn.textContent?.trim()).toBe('Applying...');
	});

	it('calls onclose from Cancel and onoverwrite from Overwrite', async () => {
		const { onclose, onoverwrite } = renderView([collision()]);
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
		expect(onclose).toHaveBeenCalledTimes(1);
		await fireEvent.click(screen.getByTestId('apply-session-overwrite'));
		expect(onoverwrite).toHaveBeenCalledTimes(1);
	});
});
