import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/testing/render';
import MusicSearchForm from '../MusicSearchForm.svelte';
import { createJob } from '../../../../__fixtures__/job';

function renderForm(
	overrides: { job?: ReturnType<typeof createJob>; discTrackCount?: number; searching?: boolean } = {}
) {
	const onsearch = vi.fn();
	renderComponent(MusicSearchForm, {
		props: { job: createJob(), discTrackCount: 0, searching: false, onsearch, ...overrides }
	});
	return onsearch;
}

const queryInput = () => screen.getByPlaceholderText('Album or title...') as HTMLInputElement;
const artistInput = () => screen.getByPlaceholderText('Artist (optional)') as HTMLInputElement;
const countryInput = () => screen.getByPlaceholderText('US, GB...') as HTMLInputElement;
const searchButton = () => screen.getByRole('button', { name: /Search/ }) as HTMLButtonElement;
const selectFor = (label: string) => screen.getByText(label).closest('label')!.querySelector('select')!;

describe('MusicSearchForm', () => {
	afterEach(() => cleanup());

	describe('seeding', () => {
		it('seeds the query from the job title and the artist from the music metadata', () => {
			renderForm({
				job: createJob({ title: 'Kind of Blue', metadata_json: { music: { album: 'Other', artist: 'Miles Davis' } } })
			});
			expect(queryInput().value).toBe('Kind of Blue');
			expect(artistInput().value).toBe('Miles Davis');
		});

		it('falls back to the music album when the job has no title', () => {
			renderForm({ job: createJob({ title: '', metadata_json: { music: { album: 'Blue Train' } } }) });
			expect(queryInput().value).toBe('Blue Train');
			expect(artistInput().value).toBe('');
		});

		it('leaves the query empty with no title and no album', () => {
			renderForm({ job: createJob({ title: '', metadata_json: {} }) });
			expect(queryInput().value).toBe('');
		});
	});

	it('selects the query text when the query input gains focus', async () => {
		renderForm();
		const select = vi.spyOn(queryInput(), 'select');
		await fireEvent.focus(queryInput());
		expect(select).toHaveBeenCalledOnce();
	});

	describe('match box', () => {
		it('is absent when the disc has no tracks', () => {
			renderForm({ discTrackCount: 0 });
			expect(screen.queryByRole('checkbox')).toBeNull();
		});

		it('is checked and shows the track count when the disc has tracks', () => {
			renderForm({ discTrackCount: 12 });
			expect(screen.getByRole('checkbox')).toBeChecked();
			expect(screen.getByText('12 tracks')).toBeInTheDocument();
		});
	});

	describe('Search button', () => {
		it('is disabled with a blank query', async () => {
			renderForm({ job: createJob({ title: '' }) });
			expect(searchButton()).toBeDisabled();
			await fireEvent.input(queryInput(), { target: { value: '   ' } });
			expect(searchButton()).toBeDisabled();
		});

		it('is disabled and reads Searching... while searching', () => {
			renderForm({ searching: true });
			const btn = screen.getByRole('button', { name: 'Searching...' });
			expect(btn).toBeDisabled();
		});

		it('is enabled with a query and reads Search', () => {
			renderForm();
			expect(searchButton()).toBeEnabled();
			expect(searchButton()).toHaveTextContent('Search');
		});
	});

	describe('searching', () => {
		it('calls onsearch with the trimmed query and the options when Search is clicked', async () => {
			const onsearch = renderForm();
			await fireEvent.input(queryInput(), { target: { value: '  Abbey Road  ' } });
			await fireEvent.click(searchButton());
			expect(onsearch).toHaveBeenCalledExactlyOnceWith('Abbey Road', {});
		});

		it.each([
			['query', queryInput],
			['artist', artistInput],
			['country', countryInput]
		])('searches on Enter in the %s input', async (_name, input) => {
			const onsearch = renderForm();
			await fireEvent.keyDown(input(), { key: 'Enter' });
			expect(onsearch).toHaveBeenCalledExactlyOnceWith('Test Movie', {});
		});

		it('does not search on another key', async () => {
			const onsearch = renderForm();
			await fireEvent.keyDown(queryInput(), { key: 'a' });
			expect(onsearch).not.toHaveBeenCalled();
		});

		it('calls nothing on Enter with a blank query', async () => {
			const onsearch = renderForm({ job: createJob({ title: '' }) });
			await fireEvent.keyDown(queryInput(), { key: 'Enter' });
			expect(onsearch).not.toHaveBeenCalled();
		});

		it('passes every filter set in the options', async () => {
			const onsearch = renderForm({ discTrackCount: 9 });
			await fireEvent.input(artistInput(), { target: { value: ' Beatles ' } });
			await fireEvent.change(selectFor('Type'), { target: { value: 'album' } });
			await fireEvent.change(selectFor('Format'), { target: { value: 'CD' } });
			await fireEvent.input(countryInput(), { target: { value: ' GB ' } });
			await fireEvent.change(selectFor('Status'), { target: { value: 'official' } });
			await fireEvent.click(searchButton());
			expect(onsearch).toHaveBeenCalledExactlyOnceWith('Test Movie', {
				artist: 'Beatles',
				track_count: 9,
				release_type: 'album',
				format: 'CD',
				country: 'GB',
				status: 'official'
			});
		});

		it('leaves the track count out when the box is unchecked', async () => {
			const onsearch = renderForm({ discTrackCount: 9 });
			await fireEvent.click(screen.getByRole('checkbox'));
			await fireEvent.click(searchButton());
			expect(onsearch).toHaveBeenCalledExactlyOnceWith('Test Movie', {});
		});
	});

	describe('Clear', () => {
		it('is hidden with no active filter', () => {
			renderForm();
			expect(screen.queryByRole('button', { name: 'Clear' })).toBeNull();
		});

		it('is shown once a filter is set', async () => {
			renderForm();
			await fireEvent.change(selectFor('Type'), { target: { value: 'live' } });
			expect(screen.getByRole('button', { name: 'Clear' })).toBeInTheDocument();
		});

		it('empties the four filters and unchecks the box when clicked', async () => {
			renderForm({ discTrackCount: 5 });
			await fireEvent.change(selectFor('Type'), { target: { value: 'live' } });
			await fireEvent.change(selectFor('Format'), { target: { value: 'Vinyl' } });
			await fireEvent.input(countryInput(), { target: { value: 'US' } });
			await fireEvent.change(selectFor('Status'), { target: { value: 'bootleg' } });
			await fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
			expect(selectFor('Type').value).toBe('');
			expect(selectFor('Format').value).toBe('');
			expect(countryInput().value).toBe('');
			expect(selectFor('Status').value).toBe('');
			expect(screen.getByRole('checkbox')).not.toBeChecked();
			expect(screen.queryByRole('button', { name: 'Clear' })).toBeNull();
		});
	});
});
