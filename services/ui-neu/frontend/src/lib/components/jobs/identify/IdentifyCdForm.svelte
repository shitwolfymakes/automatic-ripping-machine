<script lang="ts">
	// The identify dialog's fields for an audio CD (album, year, artist and one
	// title per scanned track), bound to the dialog's state.
	interface Props {
		/** Album title. */
		album: string;
		/** Release year, or null when unknown. */
		year: number | null;
		/** Album artist. */
		artist: string;
		/** One title per scanned track. */
		trackTitles: string[];
		/** Number of titles found by the scan; 0 when unknown. */
		scanTrackCount: number;
		/** Disables every input while the dialog saves. */
		submitting: boolean;
	}

	let {
		album = $bindable(),
		year = $bindable(),
		artist = $bindable(),
		trackTitles = $bindable(),
		scanTrackCount,
		submitting
	}: Props = $props();
</script>

<div class="mb-3 flex gap-3">
	<label class="field identify-dialog-field-wide">
		<span class="field-label">Album</span>
		<input bind:value={album} type="text" required data-testid="identify-album" disabled={submitting} />
	</label>
	<label class="field flex-1">
		<span class="field-label">Year</span>
		<input bind:value={year} type="number" min="1888" max="2100" data-testid="identify-year" disabled={submitting} />
	</label>
</div>
<div class="mb-3">
	<label class="field">
		<span class="field-label">Artist</span>
		<input bind:value={artist} type="text" required data-testid="identify-artist" disabled={submitting} />
	</label>
</div>
{#if scanTrackCount > 0}
	<div class="mb-3">
		<div class="field-label mb-1">Track titles</div>
		{#each trackTitles as _t, idx (idx)}
			<div class="mb-1 flex items-center gap-2">
				<span class="w-8 identify-dialog-track-index">
					{String(idx + 1).padStart(2, '0')}
				</span>
				<input
					bind:value={trackTitles[idx]}
					type="text"
					data-testid={`identify-track-${idx + 1}`}
					disabled={submitting}
					class="field-control flex-1"
				/>
			</div>
		{/each}
	</div>
{:else}
	<p class="field-help mb-3">
		Track count couldn't be determined from the scan; transcoded filenames will fall back to generic names.
	</p>
{/if}

<style>
	.identify-dialog-track-index {
		text-align: right;
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	.identify-dialog-field-wide {
		flex: 2 1 0%;
	}
</style>
