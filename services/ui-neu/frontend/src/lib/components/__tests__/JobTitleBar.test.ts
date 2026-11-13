import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createRawSnippet } from 'svelte';
import { renderComponent, screen, fireEvent, waitFor, cleanup } from '$lib/test-utils';
import JobTitleBar from '../JobTitleBar.svelte';
import { createJob, createJobDetail } from '$lib/components/__fixtures__/job';
import { JobDetail } from '$lib/stores/job-detail.svelte';
import * as authStore from '$lib/stores/auth';
import type { JobView } from '$lib/types/api.gen';

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		// Test-only helper - not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});

const setRole = (authStore as unknown as { __setRole: (r: string | null) => void }).__setRole;

const children = createRawSnippet(() => ({ render: () => '<span data-testid="actions">actions</span>' }));

function render(job: JobView) {
	const jobDetail = new JobDetail(() => 'job_1');
	jobDetail.detail = createJobDetail({ ...job, tracks: [] });
	const onsavetitle = vi.fn().mockResolvedValue(undefined);
	renderComponent(JobTitleBar, { job: jobDetail.detail.job, jobDetail, onsavetitle, children });
	return { onsavetitle };
}

const withMeta = (job: Partial<JobView>, imdb?: string, armServer: Record<string, unknown> = {}) =>
	createJob({
		...job,
		metadata_json: {
			identity: { provider: 'omdb', external_ids: imdb ? { imdb } : {} },
			provider_raw: { arm_server: armServer }
		}
	});

beforeEach(() => setRole('admin'));
afterEach(cleanup);

describe('JobTitleBar', () => {
	it('shows the title and renders the children', () => {
		render(createJob({ title: 'Alien' }));
		expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Alien');
		expect(screen.getByTestId('actions')).toBeInTheDocument();
	});

	it('shows Untitled when the job has no title', () => {
		render(createJob({ title: null }));
		expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Untitled');
	});

	it('edits the title for an admin on a job that can be resolved, saving the raw value', async () => {
		const { onsavetitle } = render(createJob({ status: 'awaiting_user_id' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Edit Title' }));
		const input = screen.getByRole('textbox', { name: 'Title' });
		await fireEvent.input(input, { target: { value: 'New Name' } });
		await fireEvent.keyDown(input, { key: 'Enter' });
		await waitFor(() => expect(onsavetitle).toHaveBeenCalledWith('New Name'));
	});

	it('does not offer title editing for a guest', () => {
		setRole('guest');
		render(createJob({ status: 'awaiting_user_id' }));
		expect(screen.queryByRole('button', { name: 'Edit Title' })).not.toBeInTheDocument();
	});

	it('does not offer title editing when the job cannot be resolved', () => {
		render(createJob({ status: 'ripping' }));
		expect(screen.queryByRole('button', { name: 'Edit Title' })).not.toBeInTheDocument();
	});

	it('shows the year when there is one', () => {
		render(createJob({ year: 1979 }));
		expect(screen.getByText('(1979)')).toBeInTheDocument();
	});

	it('shows no year when there is none', () => {
		render(createJob({ year: null }));
		expect(screen.queryByText(/^\(\d+\)$/)).not.toBeInTheDocument();
	});

	it('shows the status badge', () => {
		render(createJob({ status: 'ripping' }));
		expect(document.querySelector('.status-badge')).toBeInTheDocument();
	});

	it('shows a guest Movie text on a video disc', () => {
		setRole('guest');
		render(createJob({ disc_type: 'dvd', media_type: 'movie' }));
		expect(screen.getByTestId('media-type-text')).toHaveTextContent('Movie');
	});

	it('shows a guest TV text on a video disc', () => {
		setRole('guest');
		render(createJob({ disc_type: 'bluray', media_type: 'tv' }));
		expect(screen.getByTestId('media-type-text')).toHaveTextContent('TV');
	});

	it('shows no media type text for a guest on a CD', () => {
		setRole('guest');
		render(createJob({ disc_type: 'cd' }));
		expect(screen.queryByTestId('media-type-text')).not.toBeInTheDocument();
	});

	it('shows no media type text for an admin', () => {
		render(createJob({ disc_type: 'dvd' }));
		expect(screen.queryByTestId('media-type-text')).not.toBeInTheDocument();
	});

	it('links the IMDb badge on a video disc with an IMDb id', () => {
		render(withMeta({ disc_type: 'bluray' }, 'tt0078748'));
		expect(screen.getByRole('link', { name: 'IMDb' })).toHaveAttribute('href', 'https://www.imdb.com/title/tt0078748');
	});

	it('shows no IMDb badge on a CD', () => {
		render(withMeta({ disc_type: 'cd' }, 'tt0078748'));
		expect(screen.queryByRole('link', { name: 'IMDb' })).not.toBeInTheDocument();
	});

	it('shows no IMDb badge without an IMDb id', () => {
		render(withMeta({ disc_type: 'bluray' }));
		expect(screen.queryByRole('link', { name: 'IMDb' })).not.toBeInTheDocument();
	});

	it('shows the Multi-Title badge for a multi-title job', () => {
		render(withMeta({}, undefined, { multi_title: true }));
		expect(screen.getByText('Multi-Title')).toBeInTheDocument();
	});

	it('shows no Multi-Title badge otherwise', () => {
		render(withMeta({}));
		expect(screen.queryByText('Multi-Title')).not.toBeInTheDocument();
	});

	it('shows the ISO badge for an ISO source', () => {
		render(withMeta({}, undefined, { source_type: 'iso' }));
		expect(screen.getByText('ISO')).toBeInTheDocument();
		expect(screen.queryByText('Folder')).not.toBeInTheDocument();
	});

	it('shows the Folder badge for a folder source', () => {
		render(withMeta({}, undefined, { source_type: 'folder' }));
		expect(screen.getByText('Folder')).toBeInTheDocument();
		expect(screen.queryByText('ISO')).not.toBeInTheDocument();
	});

	it('shows neither source badge for another source', () => {
		render(withMeta({}, undefined, { source_type: 'disc' }));
		expect(screen.queryByText('ISO')).not.toBeInTheDocument();
		expect(screen.queryByText('Folder')).not.toBeInTheDocument();
	});
});
