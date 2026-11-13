import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import JobPanelTabs from '../JobPanelTabs.svelte';
import { createJob, createJobDetail } from '$lib/components/__fixtures__/job';
import { JobDetail } from '$lib/stores/job-detail.svelte';
import { JobPanels } from '$lib/stores/job-panels.svelte';
import type { JobView } from '$lib/types/api.gen';

function render(fields: Partial<JobView>) {
	const jobDetail = new JobDetail(() => 'job_1');
	jobDetail.detail = { ...createJobDetail(), job: createJob(fields) };
	const panels = new JobPanels();
	renderComponent(JobPanelTabs, { job: jobDetail.detail.job, jobDetail, panels });
	return panels;
}

const title = () => screen.queryByRole('button', { name: 'Poster & metadata search' });
const episodes = () => screen.queryByRole('button', { name: 'Match Episodes' });
const music = () => screen.queryByRole('button', { name: 'Match CD' });

describe('JobPanelTabs', () => {
	afterEach(() => cleanup());

	it.each(['dvd', 'bluray'] as const)('shows only the title search tab for a movie %s', (disc_type) => {
		render({ disc_type, media_type: 'movie' });
		expect(title()).not.toBeNull();
		expect(episodes()).toBeNull();
		expect(music()).toBeNull();
	});

	it('also shows Match Episodes for a TV video disc', () => {
		render({ disc_type: 'dvd', media_type: 'tv' });
		expect(title()).not.toBeNull();
		expect(episodes()).not.toBeNull();
		expect(music()).toBeNull();
	});

	it('shows only Match CD for a CD', () => {
		render({ disc_type: 'cd' });
		expect(music()).not.toBeNull();
		expect(title()).toBeNull();
		expect(episodes()).toBeNull();
	});

	it('shows no bar for another disc type', () => {
		render({ disc_type: 'data' });
		expect(screen.queryAllByRole('button')).toHaveLength(0);
	});

	it('toggles the title and episodes panels and follows panels.active', async () => {
		const panels = render({ disc_type: 'dvd', media_type: 'tv' });
		expect(title()!.getAttribute('aria-pressed')).toBe('false');
		await fireEvent.click(title()!);
		expect(panels.active).toBe('title');
		expect(title()!.getAttribute('aria-pressed')).toBe('true');
		await fireEvent.click(episodes()!);
		expect(panels.active).toBe('episodes');
		expect(title()!.getAttribute('aria-pressed')).toBe('false');
		expect(episodes()!.getAttribute('aria-pressed')).toBe('true');
		await fireEvent.click(episodes()!);
		expect(panels.active).toBeNull();
		expect(episodes()!.getAttribute('aria-pressed')).toBe('false');
	});

	it('toggles the music panel from the CD tab', async () => {
		const panels = render({ disc_type: 'cd' });
		await fireEvent.click(music()!);
		expect(panels.active).toBe('music');
		expect(music()!.getAttribute('aria-pressed')).toBe('true');
		await fireEvent.click(music()!);
		expect(panels.active).toBeNull();
		expect(music()!.getAttribute('aria-pressed')).toBe('false');
	});
});
