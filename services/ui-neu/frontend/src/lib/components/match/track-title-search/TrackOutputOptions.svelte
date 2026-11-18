<script lang="ts">
	import { errorMessage } from '$lib/utils/errors';
	// The track title override's output options box, with its save.
	import type { TrackView } from '$lib/types/api.gen';
	import { trackOptionsBody } from '$lib/jobs/track-edit';
	import { updateTrack } from '$lib/api/jobs';

	interface Props {
		/** The job the track belongs to. */
		jobId: string;
		/** The track; seeds the three fields once. */
		track: TrackView;
		/** The episode inputs show, and are saved, only on a series track. */
		isSeries: boolean;
		/** Sets the panel's shared outcome line. */
		onfeedback: (feedback: { type: 'success' | 'error'; message: string } | null) => void;
		/** The options were saved. */
		onsaved: () => void;
	}

	let { jobId, track, isSeries, onfeedback, onsaved }: Props = $props();

	let editFilename = $state(track.custom_filename ?? '');
	let editEpisodeNum = $state(track.episode_number != null ? String(track.episode_number) : '');
	let editEpisodeName = $state(track.episode_name ?? '');
	let savingOptions = $state(false);

	async function saveOptions() {
		savingOptions = true;
		onfeedback(null);
		try {
			await updateTrack(
				jobId,
				track.id,
				trackOptionsBody(
					{ filename: editFilename, episodeNumber: editEpisodeNum, episodeName: editEpisodeName },
					isSeries
				)
			);
			onfeedback({ type: 'success', message: 'Track options saved' });
			onsaved();
		} catch (e) {
			onfeedback({ type: 'error', message: errorMessage(e, 'Save failed') });
		} finally {
			savingOptions = false;
		}
	}
</script>

<div class="stack-sm stack track-title-search-options">
	<div class="flex flex-wrap items-end gap-1.5">
		<label class="field flex-1 track-title-search-min">
			<span class="field-label track-title-search-tiny-label">Custom filename</span>
			<input type="text" bind:value={editFilename} placeholder="Custom filename (optional)" />
		</label>
		{#if isSeries}
			<label class="field w-20">
				<span class="field-label track-title-search-tiny-label">Episode</span>
				<input type="text" bind:value={editEpisodeNum} placeholder="Episode #" />
			</label>
			<label class="field flex-1 track-title-search-episode-name-min">
				<span class="field-label track-title-search-tiny-label">Episode name</span>
				<input type="text" bind:value={editEpisodeName} placeholder="Episode name" />
			</label>
		{/if}
		<button onclick={saveOptions} disabled={savingOptions} class="btn btn-primary track-title-search-action-btn">
			{savingOptions ? 'Saving...' : 'Save options'}
		</button>
	</div>
</div>

<style>
	.track-title-search-min {
		min-width: 150px;
	}
	.track-title-search-episode-name-min {
		min-width: 120px;
	}
	/* the original buttons were px-2 py-1 text-xs (0.5rem/0.25rem, 12px/16px) -
	   .btn-sm's own padding (0.75rem/0.25rem) and line-height (inherited
	   1.25rem) both differ */
	.track-title-search-action-btn {
		min-height: auto;
		padding: 0.25rem 0.5rem;
		font-size: 0.75rem;
		line-height: 1rem;
		border: 0;
	}
	.track-title-search-options {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		background: color-mix(in srgb, var(--color-page) 40%, transparent);
		padding: 0.5rem;
	}
	.track-title-search-tiny-label {
		font-size: 10px;
		line-height: normal;
	}
</style>
