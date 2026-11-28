import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent, waitFor } from '$lib/testing/render';
import { patchJob, updateTrack } from '$lib/api/jobs';
import VersionSetChoice from '../VersionSetChoice.svelte';
import { groupVersions, isVersionSet, type VersionSet } from '$lib/jobs/version-sets';
import { refIndexOf } from '$lib/jobs/title-class';
import { trackToRow } from '$lib/jobs/review-rows';
import { bladeRunnerTracks } from '../../../__fixtures__/version-sets';
import { createJob } from '../../../__fixtures__/job';
import type { TrackView } from '$lib/types/api.gen';

vi.mock('$lib/api/jobs', () => ({ patchJob: vi.fn(), updateTrack: vi.fn() }));

const THREE = ['00334.mpls:1', '00334.mpls:2', '00342.mpls'];

function setOf(tracks: TrackView[]): VersionSet {
	const refIndex = refIndexOf(tracks);
	const found = groupVersions(tracks.map((t) => trackToRow(t, refIndex))).find(isVersionSet);
	if (!found) throw new Error('no set');
	return found;
}

function show(
	tracks: TrackView[],
	over: { canEdit?: boolean; status?: 'awaiting_review' | 'ripping'; onrefresh?: () => void } = {}
) {
	const onrefresh = over.onrefresh ?? vi.fn();
	renderComponent(VersionSetChoice, {
		props: {
			job: createJob({ status: over.status ?? 'awaiting_review', rip_invocation: 'per_title' }),
			set: setOf(tracks),
			tracks,
			canEdit: over.canEdit ?? true,
			onrefresh
		}
	});
	return onrefresh;
}

const three = () => bladeRunnerTracks().filter((t) => THREE.includes(t.source_ref));

beforeEach(() => {
	vi.mocked(patchJob).mockResolvedValue({} as never);
	vi.mocked(updateTrack).mockResolvedValue({} as never);
});
afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe('VersionSetChoice', () => {
	it('lists the angles and the other versions as radios, with the kept one checked', () => {
		show(three());
		expect(screen.getByRole('radio', { name: /Angle 1/ })).toBeChecked();
		expect(screen.getByRole('radio', { name: /Angle 2/ })).not.toBeChecked();
		expect(screen.getByRole('radio', { name: /#5/ })).not.toBeChecked();
		expect(screen.getByText('Same film, 1:49 shorter')).toBeInTheDocument();
		expect(screen.getByText('Same film, other angle')).toBeInTheDocument();
		expect(screen.getByText('00342.mpls')).toBeInTheDocument();
	});

	it('saves a choice as one PATCH that ticks it and unticks the others', async () => {
		const onrefresh = show(three());
		await fireEvent.click(screen.getByRole('radio', { name: /Angle 2/ }));
		await waitFor(() => expect(patchJob).toHaveBeenCalledTimes(1));
		expect(patchJob).toHaveBeenCalledWith('job_1', {
			tracks: [
				{ track_id: 'trk_3', excluded: true },
				{ track_id: 'trk_4', excluded: false },
				{ track_id: 'trk_5', excluded: true }
			]
		});
		await waitFor(() => expect(onrefresh).toHaveBeenCalled());
	});

	it('saves the copy without chapters from the other versions', async () => {
		show(three());
		await fireEvent.click(screen.getByRole('radio', { name: /#5/ }));
		await waitFor(() => expect(patchJob).toHaveBeenCalledTimes(1));
		expect(vi.mocked(patchJob).mock.calls[0][1].tracks?.map((e) => e.excluded)).toEqual([true, true, false]);
	});

	it('offers the view and the angle as separate choices, and 2D keeps the angle choice', async () => {
		const tracks = bladeRunnerTracks().filter(
			(t) => t.source_ref.startsWith('0033') || t.source_ref.startsWith('0034')
		);
		show(tracks);
		expect(screen.getByRole('radio', { name: '3D' })).toBeChecked();
		expect(screen.getByRole('radio', { name: '2D' })).not.toBeChecked();
		await fireEvent.click(screen.getByRole('radio', { name: '2D' }));
		await waitFor(() => expect(patchJob).toHaveBeenCalledTimes(1));
		// the 2D twin at angle 1 is ticked, nothing else
		const edits = vi.mocked(patchJob).mock.calls[0][1].tracks ?? [];
		expect(edits.filter((e) => e.excluded === false).map((e) => e.track_id)).toEqual(['trk_6']);
	});

	it('keeps the angle when the view changes', async () => {
		const tracks = bladeRunnerTracks().filter((t) => !['00400.mpls', '00102.mpls'].includes(t.source_ref));
		tracks.find((t) => t.source_ref === '00334.mpls:1')!.excluded = true;
		tracks.find((t) => t.source_ref === '00334.mpls:2')!.excluded = false;
		show(tracks);
		await fireEvent.click(screen.getByRole('radio', { name: '2D' }));
		await waitFor(() => expect(patchJob).toHaveBeenCalledTimes(1));
		const edits = vi.mocked(patchJob).mock.calls[0][1].tracks ?? [];
		expect(edits.filter((e) => e.excluded === false).map((e) => e.track_id)).toEqual(['trk_11']);
	});

	it('shows the angle choice of the chosen view', () => {
		show(bladeRunnerTracks());
		expect(screen.getByRole('radio', { name: /Angle 1/ })).toBeChecked();
		expect(screen.getByRole('radio', { name: /Angle 2/ })).not.toBeChecked();
	});

	it('lists a lone view and a lone angle as plain radios', () => {
		const tracks = [
			bladeRunnerTracks()[3],
			{ ...bladeRunnerTracks()[5], title_class_ref: '00334.mpls:1' }
		] as TrackView[];
		show(tracks);
		expect(screen.getAllByRole('radio')).toHaveLength(2);
	});

	it('keeps more than one through checkboxes, and ticking one saves the whole list', async () => {
		show(three());
		await fireEvent.click(screen.getByRole('checkbox', { name: 'Keep more than one' }));
		expect(patchJob).not.toHaveBeenCalled();
		expect(screen.queryAllByRole('radio')).toHaveLength(0);
		const boxes = screen.getAllByRole('checkbox', { name: /^#/ });
		expect(boxes).toHaveLength(3);
		await fireEvent.click(boxes[2]);
		await waitFor(() => expect(patchJob).toHaveBeenCalledTimes(1));
		expect(vi.mocked(patchJob).mock.calls[0][1].tracks?.map((e) => e.excluded)).toEqual([false, true, false]);
	});

	it('opens in checkbox mode when two are kept, and going back to one keeps the first', async () => {
		const tracks = three();
		tracks[2].excluded = false;
		show(tracks);
		const toggle = screen.getByRole('checkbox', { name: 'Keep more than one' });
		expect(toggle).toBeChecked();
		await fireEvent.click(toggle);
		await waitFor(() => expect(patchJob).toHaveBeenCalledTimes(1));
		expect(vi.mocked(patchJob).mock.calls[0][1].tracks?.map((e) => e.excluded)).toEqual([false, true, true]);
	});

	it('disables a title MakeMKV cannot rip, and one that was not ripped', () => {
		const tracks = three();
		tracks[1].unrippable = true;
		tracks[2].status = 'skipped';
		show(tracks, { status: 'ripping' });
		expect(screen.getByRole('radio', { name: /Angle 2/ })).toBeDisabled();
		expect(screen.getByRole('radio', { name: /#5/ })).toBeDisabled();
		expect(screen.getByRole('radio', { name: /Angle 1/ })).not.toBeDisabled();
		expect(screen.getByText("MakeMKV can't rip this")).toBeInTheDocument();
	});

	it('is read-only for a non-admin', () => {
		show(three(), { canEdit: false });
		for (const radio of screen.getAllByRole('radio')) expect(radio).toBeDisabled();
		expect(screen.getByRole('checkbox', { name: 'Keep more than one' })).toBeDisabled();
	});

	it('says what a 3D set needs, in the shared alert', () => {
		show(three());
		expect(
			screen.getByText('3D titles keep their 3D only with a passthrough session.').closest('.alert')
		).not.toBeNull();
	});

	it('shows a failed save and stays on the choice', async () => {
		vi.mocked(patchJob).mockRejectedValueOnce(new Error('boom'));
		const onrefresh = show(three());
		await fireEvent.click(screen.getByRole('radio', { name: /Angle 2/ }));
		expect(await screen.findByText(/boom/)).toBeInTheDocument();
		expect(onrefresh).not.toHaveBeenCalled();
	});

	it('names each version with its chips', () => {
		show(three());
		expect(screen.getAllByText('3D').length).toBeGreaterThan(0);
	});
});

describe('VersionSetChoice edition names', () => {
	it('names a kept version in place when more than one is kept', async () => {
		const tracks = three().map((t) => ({ ...t, excluded: false }));
		const onrefresh = show(tracks);
		const edits = screen.getAllByRole('button', { name: 'Edit Edition name' });
		expect(edits).toHaveLength(3);
		await fireEvent.click(edits[0]);
		const input = screen.getByRole('textbox', { name: 'Edition name' });
		await fireEvent.input(input, { target: { value: 'Theatrical' } });
		await fireEvent.keyDown(input, { key: 'Enter' });
		await waitFor(() => expect(onrefresh).toHaveBeenCalled());
	});
});
