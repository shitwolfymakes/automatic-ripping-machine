<script lang="ts">
	// The music search's query form, with the artist, the four filters, the
	// match-track-count box, Clear, and Enter to search.
	import type { JobView } from '$lib/types/api.gen';
	import { readJobMetadata } from '$lib/jobs/metadata';
	import {
		buildSearchOpts,
		countActiveFilters,
		type MusicSearchFilters,
		type MusicSearchOpts
	} from '$lib/music/search';

	interface Props {
		/** The job whose title and metadata seed the query and the artist. */
		job: JobView;
		/** The disc's track count, for the match box. */
		discTrackCount: number;
		/** Whether a search is running. */
		searching: boolean;
		/** Called with the trimmed query and the search options. */
		onsearch: (query: string, opts: MusicSearchOpts) => void;
	}
	let { job, discTrackCount, searching, onsearch }: Props = $props();

	// Seed from the typed `music` section (metadata_json.music.artist/.album) —
	// bare top-level metadata keys are gone post-migration (see job-fields.ts).
	const meta = readJobMetadata(job.metadata_json, job);
	let query = $state(job.title || meta.album || '');
	let artist = $state(meta.artist || '');
	let filterType = $state('');
	let filterFormat = $state('');
	let filterCountry = $state('');
	let filterStatus = $state('');
	let matchCount = $state(discTrackCount > 0);

	function currentFilters(): MusicSearchFilters {
		return {
			artist,
			type: filterType,
			format: filterFormat,
			country: filterCountry,
			status: filterStatus,
			matchCount
		};
	}

	function submit() {
		if (!query.trim()) return;
		onsearch(query.trim(), buildSearchOpts(currentFilters(), discTrackCount));
	}

	function handleSearchKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') submit();
	}

	let activeFilterCount = $derived(countActiveFilters(currentFilters(), discTrackCount));

	function clearFilters() {
		filterType = '';
		filterFormat = '';
		filterCountry = '';
		filterStatus = '';
		matchCount = false;
	}
</script>

<!-- Search panel -->
<div class="panel-section">
	<div class="flex flex-wrap items-end gap-2">
		<label class="flex-1 field music-search-field-min">
			<span class="eyebrow music-search-label">Album / Title</span>
			<input
				type="text"
				bind:value={query}
				onkeydown={handleSearchKeydown}
				onfocus={(e) => (e.target as HTMLInputElement).select()}
				placeholder="Album or title..."
			/>
		</label>
		<label class="field">
			<span class="eyebrow music-search-label">Artist</span>
			<input
				type="text"
				bind:value={artist}
				onkeydown={handleSearchKeydown}
				placeholder="Artist (optional)"
				class="w-36"
			/>
		</label>
		<label class="field">
			<span class="eyebrow music-search-label">Type</span>
			<select bind:value={filterType} class="music-search-select-sm">
				<option value="">Any</option>
				<option value="album">Album</option>
				<option value="single">Single</option>
				<option value="ep">EP</option>
				<option value="compilation">Compilation</option>
				<option value="live">Live</option>
				<option value="soundtrack">Soundtrack</option>
			</select>
		</label>
		<label class="field">
			<span class="eyebrow music-search-label">Format</span>
			<select bind:value={filterFormat} class="music-search-select-sm">
				<option value="">Any</option>
				<option value="CD">CD</option>
				<option value="Vinyl">Vinyl</option>
				<option value="Digital Media">Digital</option>
				<option value="Cassette">Cassette</option>
				<option value="SACD">SACD</option>
			</select>
		</label>
		<label class="field">
			<span class="eyebrow music-search-label">Country</span>
			<input
				type="text"
				bind:value={filterCountry}
				onkeydown={handleSearchKeydown}
				placeholder="US, GB..."
				class="w-20 music-search-select-sm"
			/>
		</label>
		<label class="field">
			<span class="eyebrow music-search-label">Status</span>
			<select bind:value={filterStatus} class="music-search-select-sm">
				<option value="">Any</option>
				<option value="official">Official</option>
				<option value="promotional">Promotional</option>
				<option value="bootleg">Bootleg</option>
			</select>
		</label>
		{#if discTrackCount > 0}
			<label class="flex items-center gap-1.5 field">
				<span class="eyebrow music-search-label">&nbsp;</span>
				<div class="flex items-center gap-1.5 music-search-checkbox-row">
					<input type="checkbox" bind:checked={matchCount} class="music-search-checkbox" />
					<span class="music-search-meta">{discTrackCount} tracks</span>
				</div>
			</label>
		{/if}
		<div class="flex items-center gap-2">
			<span class="eyebrow music-search-label">&nbsp;</span>
			<button onclick={submit} disabled={searching || !query.trim()} class="btn btn-primary music-search-action-btn">
				{searching ? 'Searching...' : 'Search'}
			</button>
			{#if activeFilterCount > 0}
				<button onclick={clearFilters} class="btn btn-ghost music-search-clear-btn"> Clear </button>
			{/if}
		</div>
	</div>
</div>

<style>
	.music-search-label {
		color: var(--color-text-muted);
	}
	.music-search-field-min {
		min-width: 160px;
	}
	.music-search-meta {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-muted);
	}
	.music-search-checkbox-row {
		padding: 0.3125rem 0;
	}
	.music-search-checkbox {
		width: 0.875rem;
		height: 0.875rem;
		border-radius: var(--radius-sm);
		accent-color: var(--color-primary);
	}
	.music-search-clear-btn:hover {
		color: var(--color-danger);
	}
	/* select/input variants one size down from field-control's default
	   (text-xs vs text-sm, tighter horizontal padding) */
	.music-search-select-sm {
		padding-left: 0.5rem;
		padding-right: 0.5rem;
		font-size: 0.75rem;
		line-height: 1rem;
	}
	/* the original action buttons were px-3 py-1.5 (0.75rem/0.375rem),
	   narrower than .btn's default */
	.music-search-action-btn {
		padding: 0.375rem 0.75rem;
		border: 0;
	}
	.music-search-clear-btn {
		padding: 0.375rem 0.5rem;
		font-size: 0.75rem;
		line-height: 1rem;
		border: 0;
	}
</style>
