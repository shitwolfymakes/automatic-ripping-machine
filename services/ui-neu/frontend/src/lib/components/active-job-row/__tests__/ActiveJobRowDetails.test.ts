// The active job row's expanded panel, rendered directly.
import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, within, cleanup } from '$lib/test-utils';
import ActiveJobRowDetails from '../ActiveJobRowDetails.svelte';
import { createJob } from '../../../__fixtures__/job';
import { getVideoTypeConfig } from '$lib/jobs/type';
import type { JobView } from '$lib/types/api.gen';

type Defaults = NonNullable<Parameters<typeof renderComponent>[1]>;

function renderDetails(overrides: Partial<JobView> = {}, props: Record<string, unknown> = {}) {
	const job = createJob(overrides);
	return renderComponent(ActiveJobRowDetails, {
		props: {
			job,
			typeConfig: getVideoTypeConfig(null, job.disc_type ?? null),
			tracksRipped: 0,
			tracksTotal: 0,
			active: false,
			progressStage: null,
			...props
		}
	} as Defaults);
}

/** The value cell that follows a label cell in the facts table. */
function valueCell(label: string): HTMLElement {
	const labelCell = screen.getByText(label, { selector: 'td' });
	return labelCell.nextElementSibling as HTMLElement;
}

describe('ActiveJobRowDetails', () => {
	afterEach(cleanup);

	it('links the title to the job page', () => {
		renderDetails({ id: 'job_9', title: 'Test Movie' });
		const link = screen.getByRole('link', { name: 'Test Movie' });
		expect(link).toHaveAttribute('href', '/jobs/job_9');
	});

	it('shows Untitled for an empty title', () => {
		renderDetails({ title: '' });
		expect(screen.getByRole('link', { name: 'Untitled' })).toBeInTheDocument();
	});

	it('falls back to a Poster alt text when the title is null', () => {
		const { container } = renderDetails({ title: null, poster_url: 'http://x/p.jpg' });
		expect(container.querySelector('img[alt="Poster"]')).not.toBeNull();
	});

	it('shows the job id', () => {
		renderDetails({ id: 'job_42' });
		expect(valueCell('Job ID')).toHaveTextContent('job_42');
	});

	it('shows the type pill with its label and colour variables', () => {
		const typeConfig = getVideoTypeConfig(null, 'bluray');
		renderDetails({ disc_type: 'bluray' }, { typeConfig });
		const pill = within(valueCell('Type')).getByText(typeConfig.label);
		expect(pill.style.getPropertyValue('--jt-bg')).toBe(typeConfig.badgeBg);
		expect(pill.style.getPropertyValue('--jt-text')).toBe(typeConfig.badgeText);
	});

	it('shows the disc icon and label when the job has a disc type', () => {
		renderDetails({ disc_type: 'bluray' });
		const cell = valueCell('Disc');
		expect(cell).toHaveTextContent('Blu-ray');
		expect(cell.querySelector('img')).toHaveAttribute('src', '/img/disc-bluray.svg');
	});

	it('shows a dash in the disc cell with no disc type', () => {
		renderDetails({ disc_type: undefined });
		const cell = valueCell('Disc');
		expect(cell).toHaveTextContent('-');
		expect(cell.querySelector('img')).toBeNull();
	});

	it('shows the year', () => {
		renderDetails({ year: 2024 });
		expect(valueCell('Year')).toHaveTextContent('2024');
	});

	it('shows a dash for a missing year', () => {
		renderDetails({ year: null });
		expect(valueCell('Year')).toHaveTextContent('-');
	});

	it('shows ripped over total tracks', () => {
		renderDetails({}, { tracksRipped: 3, tracksTotal: 8 });
		expect(valueCell('Tracks')).toHaveTextContent('3 / 8 ripped');
	});

	it('shows a dash for tracks when the total is 0', () => {
		renderDetails({}, { tracksRipped: 0, tracksTotal: 0 });
		expect(valueCell('Tracks').textContent?.trim()).toBe('-');
	});

	it('words the scratch-to-media stage in plain language', () => {
		renderDetails({}, { active: true, progressStage: 'scratch-to-media' });
		expect(valueCell('Progress')).toHaveTextContent('Copying to shared storage');
	});

	it('words the work-to-completed stage in plain language', () => {
		renderDetails({}, { active: true, progressStage: 'work-to-completed' });
		expect(valueCell('Progress')).toHaveTextContent('Moving to completed');
	});

	it('shows any other stage as the ripper named it', () => {
		renderDetails({}, { active: true, progressStage: 'ripping' });
		expect(valueCell('Progress')).toHaveTextContent('ripping');
	});

	it('shows a dash for progress when the job is not active', () => {
		renderDetails({}, { active: false, progressStage: 'ripping' });
		expect(valueCell('Progress').textContent?.trim()).toBe('-');
	});

	it('shows a dash for progress when there is no stage', () => {
		renderDetails({}, { active: true, progressStage: null });
		expect(valueCell('Progress').textContent?.trim()).toBe('-');
	});

	it('gives a CD the square large poster class', () => {
		const { container } = renderDetails({ disc_type: 'cd', poster_url: 'http://x/p.jpg' });
		expect(container.querySelector('.job-active-row-poster-lg-square')).not.toBeNull();
	});

	it('leaves the large poster class off for other discs', () => {
		const { container } = renderDetails({ disc_type: 'bluray', poster_url: 'http://x/p.jpg' });
		expect(container.querySelector('.job-active-row-poster-lg')).not.toBeNull();
		expect(container.querySelector('.job-active-row-poster-lg-square')).toBeNull();
	});
});
