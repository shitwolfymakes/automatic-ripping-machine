import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent, waitFor } from '$lib/testing/render';
import { updateTrack } from '$lib/api/jobs';
import EditionField from '../EditionField.svelte';
import { canNameVersion } from '$lib/jobs/edition';
import { bladeRunnerTracks } from '../../../__fixtures__/version-sets';

vi.mock('$lib/api/jobs', () => ({ updateTrack: vi.fn() }));

beforeEach(() => {
	vi.mocked(updateTrack).mockResolvedValue({} as never);
});
afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

function show(edition: string | null, canEdit = true) {
	const onsaved = vi.fn();
	renderComponent(EditionField, { props: { jobId: 'job_1', trackId: 'trk_1', edition, canEdit, onsaved } });
	return onsaved;
}

describe('EditionField', () => {
	it('saves the typed name and tells the owner', async () => {
		const onsaved = show(null);
		await fireEvent.click(screen.getByRole('button', { name: 'Edit Edition name' }));
		const input = screen.getByRole('textbox', { name: 'Edition name' });
		await fireEvent.input(input, { target: { value: " Director's Cut " } });
		await fireEvent.keyDown(input, { key: 'Enter' });
		await waitFor(() => expect(updateTrack).toHaveBeenCalledWith('job_1', 'trk_1', { edition: "Director's Cut" }));
		await waitFor(() => expect(onsaved).toHaveBeenCalled());
	});

	it('clears the name when the field is emptied', async () => {
		show('Theatrical');
		await fireEvent.click(screen.getByRole('button', { name: 'Edit Edition name' }));
		const input = screen.getByRole('textbox', { name: 'Edition name' });
		await fireEvent.input(input, { target: { value: '' } });
		await fireEvent.keyDown(input, { key: 'Enter' });
		await waitFor(() => expect(updateTrack).toHaveBeenCalledWith('job_1', 'trk_1', { revert_fields: ['edition'] }));
	});

	it('is read-only without edit rights', () => {
		show('Theatrical', false);
		expect(screen.queryByRole('button', { name: 'Edit Edition name' })).toBeNull();
		expect(screen.getByText('Theatrical')).toBeInTheDocument();
	});
});

describe('canNameVersion', () => {
	it('is true for members of a version set, the pick included, and false for a lone title', () => {
		const tracks = bladeRunnerTracks();
		const named = tracks.filter((t) => canNameVersion(t, tracks));
		expect(named.length).toBeGreaterThan(1);
		expect(tracks.some((t) => !canNameVersion(t, tracks))).toBe(true);
		const pick = tracks.find((t) =>
			tracks.some((o) => o.title_class_ref === t.source_ref && o.title_class === 'angle')
		);
		expect(pick && canNameVersion(pick, tracks)).toBe(true);
	});
});
