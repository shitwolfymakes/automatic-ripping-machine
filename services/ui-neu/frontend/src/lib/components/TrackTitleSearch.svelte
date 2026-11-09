<script lang="ts">
	import type { TrackView, MetadataCandidate, MediaType } from '$lib/types/api.gen';
	import { trackOptionsBody, trackTitleBody } from '$lib/utils/track-edit';
	import { searchMetadata, fetchMediaDetail, clearTrackTitle, updateTrack } from '$lib/api/jobs';
	import PosterImage from './PosterImage.svelte';
	import { isSeriesKind } from '$lib/utils/match';
	import { MetadataSearch, IMDB_LOOKUP, type SearchMessages } from '$lib/stores/metadataSearch.svelte';

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

	let editFilename = $state(track.custom_filename ?? '');
	let editEpisodeNum = $state(track.episode_number != null ? String(track.episode_number) : '');
	let editEpisodeName = $state(track.episode_name ?? '');
	let savingOptions = $state(false);
	let isSeries = $derived(track.role != null ? track.role === 'episode' : mediaType === 'tv');

	async function saveOptions() {
		savingOptions = true;
		feedback = null;
		try {
			await updateTrack(
				jobId,
				track.id,
				trackOptionsBody(
					{ filename: editFilename, episodeNumber: editEpisodeNum, episodeName: editEpisodeName },
					isSeries
				)
			);
			feedback = { type: 'success', message: 'Track options saved' };
			onapply?.();
		} catch (e) {
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Save failed' };
		} finally {
			savingOptions = false;
		}
	}

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
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Update failed' };
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
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Clear failed' };
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
		<div class="flex flex-wrap items-stretch gap-1.5">
			{#each results.slice(0, 8) as result, i (i)}
				<button
					onclick={() => handleSelect(result)}
					class="flex min-w-0 flex-1 items-center gap-1.5 track-title-search-result"
					title="{result.title}{result.year ? ` (${result.year})` : ''}"
				>
					{#if result.poster_url}
						<PosterImage url={result.poster_url} class="h-10 w-7 shrink-0 track-title-search-result-poster" />
					{/if}
					<div class="min-w-0">
						<p class="truncate track-title-search-result-title">{result.title}</p>
						<p class="truncate track-title-search-result-year">{result.year ?? ''}</p>
					</div>
				</button>
			{/each}
		</div>
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
	.track-title-search-episode-name-min {
		min-width: 120px;
	}
	/* the search button had a fixed width to keep the row stable between its
	   'Search'/'...' label states */
	.track-title-search-btn {
		width: 62px;
		justify-content: center;
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
	.track-title-search-result {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		padding: 0.25rem 0.375rem;
		text-align: left;
		transition: border-color var(--motion-fast) var(--ease);
	}
	.track-title-search-result:hover {
		border-color: var(--color-border-strong);
	}
	/* :global: forwarded through PosterImage's class prop */
	:global(.track-title-search-result-poster) {
		border-radius: var(--radius-sm);
		object-fit: cover;
	}
	.track-title-search-result-title {
		font-size: 10px;
		font-weight: 500;
		color: var(--color-text);
	}
	.track-title-search-result-year {
		font-size: 9px;
		color: var(--color-text-muted);
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
