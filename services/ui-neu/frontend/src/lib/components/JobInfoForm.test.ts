import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, waitFor, cleanup } from '$lib/test-utils';

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

	it('Start rip is always shown when resolvable, even with no edits', () => {
		renderComponent(JobInfoForm, { props: { job: job(), onstart: vi.fn() } });
		// no edits → no Save button, but Start rip is present
		expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Start rip' })).toBeInTheDocument();
	});

	it('Start saves (resolveJob) then calls onstart', async () => {
		const onstart = vi.fn();
		renderComponent(JobInfoForm, { props: { job: job(), onstart } });
		await fireEvent.click(screen.getByRole('button', { name: 'Start rip' }));
		await waitFor(() => expect(mockResolve).toHaveBeenCalledWith('job_1', {
			title: 'Star Knight',
			year: 1985,
			disc_number: null,
			disc_total: null,
			metadata: {}
		}));
		await waitFor(() => expect(onstart).toHaveBeenCalledTimes(1));
		// resolve ran before onstart
		expect(mockResolve.mock.invocationCallOrder[0]).toBeLessThan(onstart.mock.invocationCallOrder[0]);
	});

	it('with edits, the Start button reads "Save & Start rip"', async () => {
		renderComponent(JobInfoForm, { props: { job: job(), onstart: vi.fn() } });
		await fireEvent.input(screen.getByLabelText('Year'), { target: { value: '1986' } });
		expect(screen.getByRole('button', { name: 'Save & Start rip' })).toBeInTheDocument();
	});

	it('a Start failure shows error feedback and does not call onstart', async () => {
		mockResolve.mockRejectedValueOnce(new Error('resolve boom'));
		const onstart = vi.fn();
		renderComponent(JobInfoForm, { props: { job: job(), onstart } });
		await fireEvent.click(screen.getByRole('button', { name: 'Start rip' }));
		await waitFor(() => expect(screen.getByText('resolve boom')).toBeInTheDocument());
		expect(onstart).not.toHaveBeenCalled();
	});

	it('no Start button on a non-resolvable job', () => {
		renderComponent(JobInfoForm, { props: { job: job({ status: 'ripping' }), onstart: vi.fn() } });
		expect(screen.queryByRole('button', { name: /start rip/i })).not.toBeInTheDocument();
	});
});
