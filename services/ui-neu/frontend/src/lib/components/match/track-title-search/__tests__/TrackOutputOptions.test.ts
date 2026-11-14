import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, waitFor, cleanup } from '$lib/testing/render';
import TrackOutputOptions from '../TrackOutputOptions.svelte';
import { createTrack } from '../../../../__fixtures__/job';
import type { JobView, TrackView } from '$lib/types/api.gen';

vi.mock('$lib/api/jobs', () => ({
	updateTrack: vi.fn(() => Promise.resolve())
}));

import { updateTrack } from '$lib/api/jobs';
const mockUpdateTrack = vi.mocked(updateTrack);

function renderOptions(track: TrackView, isSeries: boolean) {
	const onfeedback = vi.fn();
	const onsaved = vi.fn();
	renderComponent(TrackOutputOptions, { props: { jobId: 'job_1', track, isSeries, onfeedback, onsaved } });
	return { onfeedback, onsaved };
}

describe('TrackOutputOptions', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	it('seeds the fields from the track', () => {
		renderOptions(createTrack({ custom_filename: 'my-file', episode_number: 4, episode_name: 'Pilot' }), true);
		expect(screen.getByPlaceholderText('Custom filename (optional)')).toHaveValue('my-file');
		expect(screen.getByPlaceholderText('Episode #')).toHaveValue('4');
		expect(screen.getByPlaceholderText('Episode name')).toHaveValue('Pilot');
	});

	it('seeds empty fields when the track has none', () => {
		renderOptions(createTrack({ custom_filename: null, episode_number: null, episode_name: null }), true);
		expect(screen.getByPlaceholderText('Custom filename (optional)')).toHaveValue('');
		expect(screen.getByPlaceholderText('Episode #')).toHaveValue('');
		expect(screen.getByPlaceholderText('Episode name')).toHaveValue('');
	});

	it('shows the episode inputs on a series track', () => {
		renderOptions(createTrack(), true);
		expect(screen.getByPlaceholderText('Episode #')).toBeInTheDocument();
		expect(screen.getByPlaceholderText('Episode name')).toBeInTheDocument();
	});

	it('hides the episode inputs on a non-series track', () => {
		renderOptions(createTrack(), false);
		expect(screen.getByPlaceholderText('Custom filename (optional)')).toBeInTheDocument();
		expect(screen.queryByPlaceholderText('Episode #')).not.toBeInTheDocument();
		expect(screen.queryByPlaceholderText('Episode name')).not.toBeInTheDocument();
	});

	it('saves the filename and episode fields on a series track', async () => {
		const track = createTrack({ custom_filename: ' f ', episode_number: 2, episode_name: ' Name ' });
		const { onsaved } = renderOptions(track, true);
		await fireEvent.click(screen.getByText('Save options'));
		await waitFor(() => expect(onsaved).toHaveBeenCalledTimes(1));
		expect(mockUpdateTrack).toHaveBeenCalledWith('job_1', track.id, {
			custom_filename: 'f',
			episode_number: 2,
			episode_name: 'Name'
		});
	});

	it('saves the values typed into the fields', async () => {
		const track = createTrack({ custom_filename: null, episode_number: null, episode_name: null });
		const { onsaved } = renderOptions(track, true);
		await fireEvent.input(screen.getByPlaceholderText('Custom filename (optional)'), { target: { value: 'typed' } });
		await fireEvent.input(screen.getByPlaceholderText('Episode #'), { target: { value: '7' } });
		await fireEvent.input(screen.getByPlaceholderText('Episode name'), { target: { value: 'Typed name' } });
		await fireEvent.click(screen.getByText('Save options'));
		await waitFor(() => expect(onsaved).toHaveBeenCalledTimes(1));
		expect(mockUpdateTrack).toHaveBeenCalledWith('job_1', track.id, {
			custom_filename: 'typed',
			episode_number: 7,
			episode_name: 'Typed name'
		});
	});

	it('saves only the filename on a non-series track', async () => {
		const track = createTrack({ custom_filename: 'f', episode_number: 2, episode_name: 'Name' });
		const { onsaved } = renderOptions(track, false);
		await fireEvent.click(screen.getByText('Save options'));
		await waitFor(() => expect(onsaved).toHaveBeenCalledTimes(1));
		expect(mockUpdateTrack).toHaveBeenCalledWith('job_1', track.id, { custom_filename: 'f' });
	});

	it('shows Saving... and disables the button while the save is pending', async () => {
		let resolve!: (job: JobView) => void;
		mockUpdateTrack.mockReturnValueOnce(new Promise<JobView>((r) => (resolve = r)));
		const { onsaved } = renderOptions(createTrack(), false);
		await fireEvent.click(screen.getByText('Save options'));
		const pending = screen.getByText('Saving...');
		expect(pending).toBeDisabled();
		resolve({} as JobView);
		await waitFor(() => expect(onsaved).toHaveBeenCalled());
		expect(screen.getByText('Save options')).not.toBeDisabled();
	});

	it('clears the feedback when a save starts, then reports success and saved', async () => {
		const { onfeedback, onsaved } = renderOptions(createTrack(), false);
		await fireEvent.click(screen.getByText('Save options'));
		await waitFor(() => expect(onsaved).toHaveBeenCalledTimes(1));
		expect(onfeedback).toHaveBeenNthCalledWith(1, null);
		expect(onfeedback).toHaveBeenNthCalledWith(2, { type: 'success', message: 'Track options saved' });
	});

	it('reports an Error failure message and does not signal saved', async () => {
		mockUpdateTrack.mockRejectedValueOnce(new Error('boom'));
		const { onfeedback, onsaved } = renderOptions(createTrack(), false);
		await fireEvent.click(screen.getByText('Save options'));
		await waitFor(() => expect(onfeedback).toHaveBeenCalledWith({ type: 'error', message: 'boom' }));
		expect(onsaved).not.toHaveBeenCalled();
	});

	it('reports "Save failed" for a non-Error failure and does not signal saved', async () => {
		mockUpdateTrack.mockRejectedValueOnce('nope');
		const { onfeedback, onsaved } = renderOptions(createTrack(), false);
		await fireEvent.click(screen.getByText('Save options'));
		await waitFor(() => expect(onfeedback).toHaveBeenCalledWith({ type: 'error', message: 'Save failed' }));
		expect(onsaved).not.toHaveBeenCalled();
	});
});
