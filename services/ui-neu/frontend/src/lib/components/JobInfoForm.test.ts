import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, waitFor, cleanup } from '$lib/test-utils';

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		isGuest: derived(_role, (r) => r === 'guest'),
		// Test-only helper — not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});

vi.mock('$lib/api/jobs', () => ({
	resolveJob: vi.fn()
}));
import { resolveJob } from '$lib/api/jobs';
import JobInfoForm from './JobInfoForm.svelte';

const mockResolve = vi.mocked(resolveJob);

function job(overrides: Record<string, unknown> = {}) {
	return {
		id: 'job_1',
		drive_id: 'drv_1',
		disc_type: 'dvd',
		status: 'awaiting_user_id',
		title: 'Star Knight',
		year: 1985,
		disc_number: null,
		disc_total: null,
		metadata_json: {},
		resumed_from_crash: false,
		...overrides
	} as any;
}

beforeEach(() => {
	mockResolve.mockReset();
	mockResolve.mockResolvedValue({ status: 'identified' } as any);
});

afterEach(() => {
	cleanup();
});

describe('JobInfoForm', () => {
	it('seeds Title and Year from the job', () => {
		renderComponent(JobInfoForm, { props: { job: job() } });
		expect((screen.getByLabelText('Title') as HTMLInputElement).value).toBe('Star Knight');
		expect((screen.getByLabelText('Year') as HTMLInputElement).value).toBe('1985');
	});

	it('Save calls resolveJob once with the form body', async () => {
		const onrefresh = vi.fn();
		renderComponent(JobInfoForm, { props: { job: job(), onrefresh } });
		await fireEvent.input(screen.getByLabelText('Year'), { target: { value: '1986' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(1));
		expect(mockResolve).toHaveBeenCalledWith('job_1', {
			title: 'Star Knight',
			year: 1986,
			disc_number: null,
			disc_total: null,
			metadata: {}
		});
		await waitFor(() => expect(onrefresh).toHaveBeenCalled());
	});

	it('Save sends the seeded title even on a disc-only change', async () => {
		renderComponent(JobInfoForm, { props: { job: job() } });
		await fireEvent.input(screen.getByLabelText('Disc number'), { target: { value: '2' } });
		await fireEvent.input(screen.getByLabelText('Disc total'), { target: { value: '3' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(mockResolve).toHaveBeenCalledWith('job_1', {
			title: 'Star Knight',
			year: 1985,
			disc_number: 2,
			disc_total: 3,
			metadata: {}
		}));
	});

	it('a save error shows error feedback and keeps the dirty Save bar', async () => {
		mockResolve.mockRejectedValueOnce(new Error('boom'));
		renderComponent(JobInfoForm, { props: { job: job() } });
		await fireEvent.input(screen.getByLabelText('Year'), { target: { value: '1990' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(screen.getByText('boom')).toBeInTheDocument());
		// still dirty → Save button still present
		expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();
	});

	it('blank Title disables Save', async () => {
		renderComponent(JobInfoForm, { props: { job: job() } });
		await fireEvent.input(screen.getByLabelText('Title'), { target: { value: '' } });
		// dirty now true (title touched) so Save bar shows; the button is disabled
		expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
	});

	it('a non-resolvable job renders fields read-only with the lock note', () => {
		renderComponent(JobInfoForm, { props: { job: job({ status: 'ripping' }) } });
		expect(screen.getByText(/Identity is locked/i)).toBeInTheDocument();
		expect(screen.getByLabelText('Title')).toBeDisabled();
	});

	it('does not overwrite a touched field when the job prop changes', async () => {
		const { rerender } = renderComponent(JobInfoForm, { props: { job: job() } });
		await fireEvent.input(screen.getByLabelText('Title'), { target: { value: 'My Edit' } });
		await rerender({ job: job({ title: 'Polled Title' }) });
		expect((screen.getByLabelText('Title') as HTMLInputElement).value).toBe('My Edit');
	});

	it('has no Start button — the form only saves metadata (Start lives in the action row)', async () => {
		renderComponent(JobInfoForm, { props: { job: job() } });
		expect(screen.queryByRole('button', { name: /start rip/i })).not.toBeInTheDocument();
		// editing reveals only Save + Reset
		await fireEvent.input(screen.getByLabelText('Year'), { target: { value: '1986' } });
		expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: /start/i })).not.toBeInTheDocument();
	});

	describe('guest write-control gating', () => {
		afterEach(async () => {
			const auth = (await import('$lib/stores/auth')) as unknown as {
				__setRole: (r: string | null) => void;
			};
			auth.__setRole('admin');
		});

		it('hides the Save button for guests', async () => {
			const auth = (await import('$lib/stores/auth')) as unknown as {
				__setRole: (r: string | null) => void;
			};
			auth.__setRole('guest');
			renderComponent(JobInfoForm, { props: { job: job() } });
			await fireEvent.input(screen.getByLabelText('Year'), { target: { value: '1986' } });
			expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
		});

		it('shows the Save button for admins', async () => {
			renderComponent(JobInfoForm, { props: { job: job() } });
			await fireEvent.input(screen.getByLabelText('Year'), { target: { value: '1986' } });
			expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();
		});
	});
});
