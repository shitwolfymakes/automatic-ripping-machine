<script lang="ts">
	import { errorMessage } from '$lib/utils/errors';
	import type { TrackView, MetadataCandidate, MediaType } from '$lib/types/api.gen';
	import { trackTitleBody } from '$lib/jobs/track-edit';
	import { searchMetadata, fetchMediaDetail, clearTrackTitle, updateTrack } from '$lib/api/jobs';
	import TrackOutputOptions from './track-title-search/TrackOutputOptions.svelte';
	import TrackSearchResults from './track-title-search/TrackSearchResults.svelte';
	import { isSeriesKind } from '$lib/match/match';
	import { MetadataSearch, IMDB_LOOKUP, type SearchMessages } from '$lib/stores/metadata-search.svelte';

	interface Props {
		jobId: string;
		track: TrackView;
		// The job's media type: the fallback for isSeries until a source or
		// the operator has set this title's role.
		mediaType?: MediaType | null;
		onapply?: () => void;
		onclear?: () => void;
		onclose?: () => void;
	}

	let { jobId, track, mediaType = null, onapply, onclear, onclose }: Props = $props();

	let query = $state(track.title || (track.source_ref?.replace(/\.\w+$/, '') ?? ''));
	let yearInput = $state(track.year != null ? String(track.year) : '');
	let imdbInput = $state('');
	const search = new MetadataSearch();
	let results = $state<MetadataCandidate[]>([]);

	let detail = $state<MetadataCandidate | null>(null);

	let applying = $state(false);
	let clearing = $state(false);
	let feedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	let isSeries = $derived(track.role != null ? track.role === 'episode' : mediaType === 'tv');

	// Editable fields populated from the selected candidate
	let editTitle = $state('');
	let editYear = $state('');
	let editType = $state<'movie' | 'series'>('movie');
	let editPosterUrl = $state('');

	$effect(() => {
		if (detail) {
			editTitle = detail.title;
			editYear = detail.year != null ? String(detail.year) : '';
			editType = isSeriesKind(detail.kind) ? 'series' : 'movie';
			editPosterUrl = detail.poster_url ?? '';
		}
	});

	const TEXT_SEARCH: SearchMessages = { empty: 'No results found.', failed: 'Search failed' };

	async function handleSearch() {
		const imdb = imdbInput.trim();
		if (imdb) {
			results = [];
			detail = null;
			await search.run(
				() => fetchMediaDetail(imdb),
				IMDB_LOOKUP,
				(found) => (detail = found[0] ?? null)
			);
			return;
		}
		if (!query.trim()) return;
		detail = null;
		await search.run(
			() => searchMetadata(query.trim()),
			TEXT_SEARCH,
			(found) => (results = found)
		);
	}

	function handleSelect(result: MetadataCandidate) {
		detail = result;
	}

	async function applyFromDetail() {
		applying = true;
		feedback = null;
		try {
			await updateTrack(
				jobId,
				track.id,
				trackTitleBody({
					title: editTitle,
					year: editYear,
					type: editType,
					posterUrl: editPosterUrl
				})
			);
			feedback = { type: 'success', message: 'Track title updated' };
			onapply?.();
		} catch (e) {
			feedback = { type: 'error', message: errorMessage(e, 'Update failed') };
		} finally {
			applying = false;
		}
	}

	async function handleClear() {
		clearing = true;
		feedback = null;
		try {
			await clearTrackTitle(jobId, track.id);
			feedback = { type: 'success', message: 'Reverted to job title' };
			detail = null;
			results = [];
			onclear?.();
		} catch (e) {
			feedback = { type: 'error', message: errorMessage(e, 'Clear failed') };
		} finally {
			clearing = false;
		}
	}

	function handleSearchKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') handleSearch();
	}
</script>

<div class="stack-sm stack panel-section">
	<div class="flex items-center justify-between">
		<h5 class="eyebrow">
			Track {track.index} Title Override
		</h5>
		<div class="flex items-center gap-1.5">
			{#if track.title}
				<button onclick={handleClear} disabled={clearing} class="btn btn-warning track-title-search-action-btn">
					{clearing ? 'Clearing...' : 'Clear Override'}
				</button>
			{/if}
			{#if onclose}
				<button onclick={onclose} title="Close" class="btn btn-icon">
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"
						><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg
					>
				</button>
			{/if}
		</div>
	</div>

	<!-- Search form -->
	<div class="flex flex-wrap gap-1.5">
		<input
			type="text"
			bind:value={query}
			onkeydown={handleSearchKeydown}
			placeholder="Title..."
			class="field-control flex-1 track-title-search-min"
		/>
		<input
			type="text"
			bind:value={yearInput}
			onkeydown={handleSearchKeydown}
			placeholder="Year"
			class="field-control w-16"
		/>
		<input
			type="text"
			bind:value={imdbInput}
			onkeydown={handleSearchKeydown}
			placeholder="tt..."
			class="field-control w-28"
		/>
		<button
			onclick={handleSearch}
			disabled={search.searching || (!query.trim() && !imdbInput.trim())}
			class="btn btn-primary track-title-search-btn track-title-search-action-btn"
		>
			{search.searching ? '...' : 'Search'}
		</button>
	</div>

	<!-- Track output options: custom filename + (series) episode -->
	<TrackOutputOptions {jobId} {track} {isSeries} onfeedback={(f) => (feedback = f)} onsaved={() => onapply?.()} />

	{#if search.error}
		{#if search.error.toLowerCase().includes('api key')}
			<div class="alert alert-warning">
				<p>{search.error}</p>
				<p class="mt-0.5 track-title-search-alert-hint">
					Configure API keys in <a href="/settings" class="track-title-search-alert-link">Settings</a>.
				</p>
			</div>
		{:else}
			<div class="flex items-center gap-3">
				<p class="field-help">{search.error}</p>
			</div>
		{/if}
	{/if}

	<!-- Results -->
	{#if !detail && results.length > 0}
		<TrackSearchResults {results} onselect={handleSelect} />
	{/if}

	<!-- Detail / Edit -->
	{#if detail}
		<div class="stack-sm stack">
			<div class="grid grid-cols-2 gap-2">
				<label class="field col-span-2">
					<span class="field-label track-title-search-tiny-label">Title</span>
					<input type="text" bind:value={editTitle} />
				</label>
				<label class="field">
					<span class="field-label track-title-search-tiny-label">Year</span>
					<input type="text" bind:value={editYear} />
				</label>
				<label class="field">
					<span class="field-label track-title-search-tiny-label">Type</span>
					<select bind:value={editType}>
						<option value="movie">Movie</option>
						<option value="series">Series</option>
					</select>
				</label>
				<label class="field col-span-2">
					<span class="field-label track-title-search-tiny-label">Poster URL</span>
					<input type="text" bind:value={editPosterUrl} placeholder="https://..." />
				</label>
			</div>
			<div class="flex items-center gap-2">
				<button
					onclick={applyFromDetail}
					disabled={applying || !editTitle.trim()}
					class="btn track-title-search-success-btn track-title-search-action-btn"
				>
					{applying ? 'Applying...' : 'Apply'}
				</button>
				{#if results.length > 0}
					<button
						onclick={() => {
							detail = null;
						}}
						class="btn btn-ghost track-title-search-back-btn"
					>
						Back
					</button>
				{/if}
				{#if feedback}
					<span class="track-title-search-feedback" data-tone={feedback.type}>{feedback.message}</span>
				{/if}
			</div>
		</div>
	{/if}
</div>

<style>
	.track-title-search-min {
		min-width: 150px;
	}
	/* the search button had a fixed width to keep the row stable between its
	   'Search'/'...' label states */
	.track-title-search-btn {
		width: 62px;
		justify-content: center;
	}
	/* the buttons are 0.5rem/0.25rem padding with text-xs (12px/16px) -
	   .btn-sm's own padding (0.75rem/0.25rem) and line-height (inherited
	   1.25rem) both differ */
	.track-title-search-action-btn {
		min-height: auto;
		padding: 0.25rem 0.5rem;
		font-size: 0.75rem;
		line-height: 1rem;
		border: 0;
	}
	.btn-warning.track-title-search-action-btn {
		box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-warning) 30%, transparent);
	}
	.track-title-search-back-btn {
		min-height: auto;
		padding: 0.25rem 0.5rem;
		font-size: 0.75rem;
		line-height: 1rem;
		border: 0;
	}
	.track-title-search-tiny-label {
		font-size: 10px;
		line-height: normal;
	}
	.track-title-search-alert-hint {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-on-warning-soft);
	}
	.track-title-search-alert-link {
		text-decoration: underline;
	}
	.track-title-search-alert-link:hover {
		text-decoration: none;
	}
	.track-title-search-success-btn {
		border: 0;
		background: var(--color-success);
		color: var(--color-on-primary);
	}
	.track-title-search-success-btn:hover {
		filter: brightness(0.9);
	}
	.track-title-search-feedback {
		font-size: 0.75rem;
		line-height: 1rem;
	}
	.track-title-search-feedback[data-tone='success'] {
		color: var(--color-success);
	}
	.track-title-search-feedback[data-tone='error'] {
		color: var(--color-danger);
	}
</style>
