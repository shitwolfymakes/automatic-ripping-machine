<script lang="ts">
	import type { JobView, MetadataCandidate } from '$lib/types/api.gen';
	import { searchMetadata, fetchMediaDetail, updateJobTitle, resolveJob } from '$lib/api/jobs';
	import PosterImage from './PosterImage.svelte';
	import { reveal } from '$lib/transitions';
	import { isAdmin } from '$lib/stores/auth';
	import { metadataProvider } from '$lib/stores/config';

	// Pretty label for the configured default metadata provider; generic until
	// the config store hydrates (layout load runs hydrateConfig once per load).
	const PROVIDER_LABELS: Record<string, string> = { tmdb: 'TMDb', omdb: 'OMDb' };
	let providerLabel = $derived(PROVIDER_LABELS[$metadataProvider ?? ''] ?? 'OMDb/TMDb');

	interface Props {
		job: JobView;
		onapply?: () => void;
		onepisodes?: () => void;
	}

	let { job, onapply, onepisodes }: Props = $props();

	let query = $state(job.title || '');
	let yearInput = $state(job.year != null ? String(job.year) : '');
	let imdbInput = $state('');
	let searching = $state(false);
	let results = $state<MetadataCandidate[]>([]);
	let searchError = $state<string | null>(null);

	let selected = $state<MetadataCandidate | null>(null);
	let detail = $state<MetadataCandidate | null>(null);
	let loadingDetail = $state(false);

	let applying = $state(false);
	let feedback = $state<{ type: 'success' | 'error'; message: string; showEpisodes?: boolean } | null>(null);

	// Editable metadata fields, populated from the selected candidate. On a
	// resolvable job, Apply identifies the movie via resolveJob (title/year +
	// status promotion) and saves the poster via updateJobTitle (best-effort);
	// on a non-resolvable job it falls back to poster-only (resolve would 409).
	let editTitle = $state('');
	let editYear = $state('');
	let editType = $state<'movie' | 'series'>('movie');
	let editPosterUrl = $state('');

	const RESOLVABLE_STATUSES = [
		'awaiting_user_id', 'ripped_awaiting_identify', 'identified', 'ripped', 'ripped_partial'
	];
	let canResolve = $derived(RESOLVABLE_STATUSES.includes(job.status));

	$effect(() => {
		if (detail) {
			editTitle = detail.title;
			editYear = detail.year != null ? String(detail.year) : '';
			editType = detail.kind === 'series' || detail.kind === 'tv' ? 'series' : 'movie';
			editPosterUrl = detail.poster_url ?? '';
		}
	});

	async function handleSearch() {
		const imdb = imdbInput.trim();
		if (imdb) {
			// Direct IMDb ID lookup — skip search
			searching = true;
			searchError = null;
			results = [];
			selected = null;
			detail = null;
			try {
				const resp = await fetchMediaDetail(imdb);
				detail = resp.candidates[0] ?? null;
				selected = detail;
				if (!detail) searchError = 'No match found for that IMDb ID.';
			} catch (e) {
				searchError = e instanceof Error ? e.message : 'IMDb lookup failed';
			} finally {
				searching = false;
			}
			return;
		}
		if (!query.trim()) return;
		searching = true;
		searchError = null;
		results = [];
		selected = null;
		detail = null;
		try {
			const resp = await searchMetadata(query.trim());
			results = resp.candidates;
			if (results.length === 0) {
				searchError = 'No results found. Try a different search term.';
			}
		} catch (e) {
			searchError = e instanceof Error ? e.message : 'Search failed';
		} finally {
			searching = false;
		}
	}

	function handleSelect(result: MetadataCandidate) {
		if (selected === result) {
			selected = null;
			detail = null;
			return;
		}
		selected = result;
		detail = result;
	}

	async function applyResult() {
		const title = editTitle.trim();
		if (!title) {
			feedback = { type: 'error', message: 'Title is required' };
			return;
		}
		applying = true;
		feedback = null;
		const parsedYear = editYear.trim() ? Number(editYear.trim()) : null;
		const year = Number.isFinite(parsedYear as number) ? parsedYear : null;
		const poster = editPosterUrl.trim() || null;
		const isSeries = editType === 'series';
		try {
			if (canResolve) {
				await resolveJob(job.id, { title, year, metadata: { video_type: editType } });
				let message = 'Identified';
				if (poster !== (job.poster_url_manual ?? null)) {
					try {
						await updateJobTitle(job.id, { poster_url_manual: poster });
					} catch {
						message = 'Identified; poster not saved';
					}
				}
				feedback = { type: 'success', message, showEpisodes: isSeries };
			} else {
				// Non-resolvable status (created/ripping/failed/abandoned): poster only.
				await updateJobTitle(job.id, { poster_url_manual: poster });
				feedback = { type: 'success', message: 'Poster updated', showEpisodes: isSeries };
			}
			onapply?.();
		} catch (e) {
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Apply failed' };
		} finally {
			applying = false;
		}
	}

	function backToResults() {
		detail = null;
		selected = null;
	}

	function handleSearchKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') handleSearch();
	}


</script>

<div class="stack">
	<!-- Search form -->
	<div class="flex flex-wrap gap-2">
		<input
			type="text"
			bind:value={query}
			onkeydown={handleSearchKeydown}
			onfocus={(e) => (e.target as HTMLInputElement).select()}
			placeholder="Title..."
			class="field-control flex-1 title-search-min"
		/>
		<input
			type="text"
			bind:value={yearInput}
			onkeydown={handleSearchKeydown}
			placeholder="Year"
			class="field-control w-20"
		/>
		<input
			type="text"
			bind:value={imdbInput}
			onkeydown={handleSearchKeydown}
			placeholder="IMDb ID (tt...)"
			class="field-control w-36"
		/>
		<button
			onclick={handleSearch}
			disabled={searching || (!query.trim() && !imdbInput.trim())}
			class="btn btn-primary title-search-action-btn"
		>
			{searching ? 'Searching...' : 'Search'}
		</button>
		<span class="badge badge-sm" title="Default metadata provider configured in Settings">
			{providerLabel}
		</span>
	</div>

	{#if searchError}
		{#if searchError.toLowerCase().includes('api key')}
			<div class="alert alert-warning">
				<p class="title-search-alert-title">{searchError}</p>
				<p class="mt-1 title-search-alert-hint">Configure API keys in <a href="/settings" class="title-search-alert-link">Settings</a>.</p>
			</div>
		{:else}
			<div class="flex items-center gap-3">
				<p class="field-help">{searchError}</p>
			</div>
		{/if}
	{/if}

	<!-- Results grid (hidden when detail is shown) -->
	{#if !detail && results.length > 0}
		<div class="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
			{#each results as result}
				<button
					onclick={() => handleSelect(result)}
					class="group flex flex-col overflow-hidden title-search-card"
					data-selected={selected === result}
				>
					{#if result.poster_url}
						<PosterImage url={result.poster_url} alt={result.title} class="title-search-poster w-full object-cover" />
					{:else}
						<div
							class="flex title-search-poster w-full items-center justify-center title-search-placeholder"
						>
							<svg class="h-10 w-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="1.5"
									d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z"
								/>
							</svg>
						</div>
					{/if}
					<div class="p-2">
						<p
							class="title-search-card-title line-clamp-2"
						>
							{result.title}
						</p>
						<div class="mt-1 flex items-center gap-1.5">
							<span class="title-search-card-year">{result.year ?? ''}</span>
							<span
								class="badge badge-sm"
								data-kind={result.kind === 'series' || result.kind === 'tv' ? 'series' : 'movie'}
							>
								{result.kind}
							</span>
						</div>
					</div>
				</button>
			{/each}
		</div>
	{/if}

	<!-- Detail panel with editable fields -->
	{#if loadingDetail}
		<div class="panel-section title-search-loading">
			Loading details...
		</div>
	{:else if detail}
		<div class="panel">
			<div class="stack">
				{#if results.length > 0}
					<button
						onclick={backToResults}
						class="btn btn-link inline-flex items-center gap-1"
					>
						<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
						</svg>
						Back to results
					</button>
				{/if}
				<!-- Editable fields -->
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
					<label class="field sm:col-span-2">
						<span class="field-label">Title</span>
						<input type="text" bind:value={editTitle} />
					</label>
					<label class="field">
						<span class="field-label">Year</span>
						<input type="text" bind:value={editYear} />
					</label>
					<label class="field">
						<span class="field-label">Type</span>
						<select bind:value={editType}>
							<option value="movie">Movie</option>
							<option value="series">Series</option>
						</select>
					</label>
					<label class="field sm:col-span-2">
						<span class="field-label">Poster URL</span>
						<input type="text" bind:value={editPosterUrl} placeholder="https://..." />
					</label>
				</div>
				<div class="flex items-center gap-2">
					{#if $isAdmin}
						<button
							onclick={applyResult}
							disabled={applying}
							class="btn title-search-success-btn title-search-action-btn"
						>
							{applying ? 'Applying...' : canResolve ? 'Apply' : 'Apply Poster'}
						</button>
					{/if}
					{#if feedback}
						<span
							in:reveal
							class="title-search-feedback"
							data-tone={feedback.type}
						>
							{feedback.message}
						</span>
						{#if feedback.showEpisodes && onepisodes}
							<button
								onclick={onepisodes}
								class="btn btn-primary title-search-action-btn"
							>
								Match Episodes
							</button>
						{/if}
					{/if}
				</div>
			</div>
		</div>
	{/if}
</div>

<style>
	.title-search-min { min-width: 200px; }
	/* the original action buttons were px-3 py-1.5 (0.75rem/0.375rem),
	   narrower than .btn's default 1rem/0.5rem */
	.title-search-action-btn { padding: 0.375rem 0.75rem; }
	/* :global: also passed as PosterImage's class prop, landing on its own <img> */
	:global(.title-search-poster) { aspect-ratio: 2 / 3; }
	.title-search-alert-title { font-weight: 500; }
	.title-search-alert-link { text-decoration: underline; }
	.title-search-alert-link:hover { text-decoration: none; }
	.title-search-alert-hint { font-size: 0.75rem; line-height: 1rem; color: var(--color-on-warning-soft); }
	.title-search-card { border: 1px solid var(--color-border); border-radius: var(--radius-lg); text-align: left; transition: border-color var(--motion-fast) var(--ease); }
	.title-search-card:hover { border-color: var(--color-border-strong); }
	.title-search-card[data-selected="true"] { border-color: var(--color-primary); box-shadow: 0 0 0 2px color-mix(in srgb, var(--color-primary) 30%, transparent); }
	.title-search-placeholder { background: var(--color-primary-tint-2); color: var(--color-text-faint); }
	.title-search-card-title { font-size: 0.875rem; line-height: 1.25rem; font-weight: 500; color: var(--color-text); }
	.title-search-card:hover .title-search-card-title { color: var(--color-primary-text); }
	.title-search-card-year { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
	.title-search-loading { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	.title-search-success-btn { border: 0; background: var(--color-success); color: var(--color-on-primary); }
	.title-search-success-btn:hover { filter: brightness(0.9); }
	.title-search-feedback { font-size: 0.75rem; line-height: 1rem; }
	.title-search-feedback[data-tone="success"] { color: var(--color-success); }
	.title-search-feedback[data-tone="error"] { color: var(--color-danger); }
	/* result kind pill: series -> accent-3 (violet, no tone matches purple);
	   movie -> success tone (closest to the original's green) */
	.badge[data-kind="series"] { background: color-mix(in srgb, var(--color-accent-3) 15%, transparent); color: var(--color-accent-3); text-transform: uppercase; }
	.badge[data-kind="movie"] { background: var(--color-success-soft); color: var(--color-on-success-soft); text-transform: uppercase; }
</style>
