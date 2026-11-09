<script lang="ts">
	import type { JobView, MetadataCandidate, ResolveResponse } from '$lib/types/api.gen';
	import { searchMetadata, fetchMediaDetail, updateJobTitle, resolveJob } from '$lib/api/jobs';
	import { titleMatchBody, titleResolveBody, type TitleApplyValues } from '$lib/utils/job-resolve';
	import MatchPicker from './match/MatchPicker.svelte';
	import { isSeriesKind } from '$lib/utils/match';
	import { reveal } from '$lib/transitions';
	import { isAdmin } from '$lib/stores/auth';
	import { searchProviders, keyedSources } from '$lib/stores/config';
	import { SEARCH_SOURCES, chooseSource, type SearchSource } from '$lib/utils/search-providers';
	import TitleSourcePicker from './title-search/TitleSourcePicker.svelte';
	import { MetadataSearch, IMDB_LOOKUP, type SearchMessages } from '$lib/stores/metadataSearch.svelte';

	interface Props {
		job: JobView;
		onapply?: () => void;
		/** Called with the resolve response when Apply identified the job. */
		onresolved?: (resp: ResolveResponse) => void;
		onseries?: () => void;
		initialType?: 'movie' | 'tv';
	}

	let { job, onapply, onresolved, onseries, initialType }: Props = $props();

	// Search type: the caller's hint, else the job's type (set by the Movie/TV
	// switch on the job), else TV for a disc that looks episodic.
	let searchType = $derived<'movie' | 'tv'>(
		initialType ?? (job.media_type === 'tv' || (job.media_type == null && job.looks_episodic) ? 'tv' : 'movie')
	);

	// Source picker: the provider for this search. Defaults to the Settings
	// choice for the search type (until the operator picks one); a type change
	// drops the pick. A keyed source without a saved key is disabled.
	let pickedSource = $state<SearchSource | null>(null);
	let sourceOptions = $derived(SEARCH_SOURCES[searchType]);
	let source = $derived(
		chooseSource(
			sourceOptions,
			pickedSource,
			searchType === 'tv' ? $searchProviders.tv : $searchProviders.movie,
			$keyedSources
		)
	);

	// The job's type changed (Movie/TV switch): the old pick and results belong
	// to the other type.
	let lastSearchType: 'movie' | 'tv' | undefined;
	$effect(() => {
		const t = searchType;
		if (lastSearchType !== undefined && t !== lastSearchType) {
			pickedSource = null;
			closeResults();
			search.error = null;
		}
		lastSearchType = t;
	});

	let query = $state(job.title || '');
	let yearInput = $state(job.year != null ? String(job.year) : '');
	let imdbInput = $state('');
	const search = new MetadataSearch();
	let results = $state<MetadataCandidate[]>([]);

	let applying = $state(false);
	// Tagged with the row and result list a Use started on, so a result that
	// lands after the operator moved on is not shown under another row.
	let feedback = $state<{ type: 'success' | 'error'; message: string; row: number; list: number } | null>(null);
	let listGen = $state(0);

	// Editable metadata fields, populated from the selected candidate. On a
	// resolvable job, Apply identifies the movie via resolveJob (title/year +
	// status promotion) and saves the poster via updateJobTitle (best-effort);
	// on a non-resolvable job it falls back to poster-only (resolve would 409).
	let editTitle = $state('');
	let editYear = $state('');
	let editType = $state<'movie' | 'series'>('movie');
	let editPosterUrl = $state('');

	let canResolve = $derived(job.actions.can_resolve);

	// "Edit before using": the edit fields start from the selected match and,
	// once opened, are what Use applies (spec 4.2).
	let editing = $state(false);
	// The picker owns the selection; this only spots a row change.
	let selectedIndex = $state(-1);
	// True once the operator typed in the poster field; only then is the poster theirs.
	let posterEdited = $state(false);

	function fillEdit(c: MetadataCandidate) {
		editTitle = c.title;
		editYear = c.year != null ? String(c.year) : '';
		editType = isSeriesKind(c.kind) ? 'series' : 'movie';
		editPosterUrl = c.poster_url ?? '';
		posterEdited = false;
	}

	function handlePickerSelect(_c: MetadataCandidate, index: number) {
		// Feedback is kept: it shows again only under the row it is for.
		if (index !== selectedIndex) {
			editing = false;
			posterEdited = false;
		}
		selectedIndex = index;
	}

	function toggleEdit(c: MetadataCandidate) {
		if (!editing) fillEdit(c);
		editing = !editing;
	}

	function closeResults() {
		results = [];
		listGen++;
		selectedIndex = -1;
		editing = false;
		posterEdited = false;
	}

	let providerLabel = $derived(sourceOptions.find((o) => o.id === source)?.label ?? '');
	let parsedSearchYear = $derived(/^\d{4}$/.test(yearInput.trim()) ? Number(yearInput.trim()) : null);

	const TEXT_SEARCH: SearchMessages = {
		empty: 'No results found. Try a different search term.',
		failed: 'Search failed'
	};

	async function handleSearch() {
		const imdb = imdbInput.trim();
		if (imdb) {
			// Direct IMDb ID lookup — skip search
			closeResults();
			results = (await search.run(() => fetchMediaDetail(imdb), IMDB_LOOKUP)).slice(0, 1);
			return;
		}
		if (!query.trim()) return;
		closeResults();
		results = await search.run(() => searchMetadata(query.trim(), searchType, source, parsedSearchYear), TEXT_SEARCH);
	}

	async function applyResult(c: MetadataCandidate) {
		const at = { row: selectedIndex, list: listGen };
		const values: TitleApplyValues = editing
			? {
					title: editTitle.trim(),
					year: editYear.trim(),
					isSeries: editType === 'series',
					poster: posterEdited ? editPosterUrl.trim() || null : (c.poster_url ?? null)
				}
			: {
					title: c.title,
					year: c.year != null ? String(c.year) : '',
					isSeries: isSeriesKind(c.kind),
					poster: c.poster_url ?? null
				};
		if (!values.title) {
			feedback = { type: 'error', message: 'Title is required', ...at };
			return;
		}
		applying = true;
		feedback = null;
		// The candidate's ids name a title of its own kind; after a type edit they don't apply.
		const idsApply = isSeriesKind(c.kind) === values.isSeries;
		let resolved: ResolveResponse | undefined;
		try {
			if (canResolve && idsApply && c.provider) {
				resolved = await resolveJob(job.id, titleMatchBody(c, values, editing && posterEdited));
				feedback = { type: 'success', message: 'Identified', ...at };
			} else if (canResolve) {
				resolved = await resolveJob(job.id, titleResolveBody(values));
				let message = 'Identified';
				if (values.poster !== (job.poster_url_manual ?? null)) {
					try {
						await updateJobTitle(job.id, { poster_url_manual: values.poster });
					} catch {
						message = 'Identified; poster not saved';
					}
				}
				feedback = { type: 'success', message, ...at };
			} else {
				// Non-resolvable status (created/ripping/failed/abandoned): poster only.
				await updateJobTitle(job.id, { poster_url_manual: values.poster });
				feedback = { type: 'success', message: 'Poster updated', ...at };
			}
			if (resolved) onresolved?.(resolved);
			// Episode matching only starts after a resolve; a poster-only save is a plain apply.
			if (values.isSeries && canResolve) onseries?.();
			else onapply?.();
		} catch (e) {
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Apply failed', ...at };
		} finally {
			applying = false;
		}
	}

	function handleSearchKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') handleSearch();
	}
</script>

<div class="stack">
	<!-- Search form -->
	<div class="flex flex-wrap gap-2">
		<div class="flex flex-1 title-search-min title-search-query">
			<TitleSourcePicker options={sourceOptions} {source} keyed={$keyedSources} onpick={(id) => (pickedSource = id)} />
			<input
				type="text"
				bind:value={query}
				onkeydown={handleSearchKeydown}
				onfocus={(e) => (e.target as HTMLInputElement).select()}
				placeholder="Title..."
				aria-label="Title"
				class="field-control flex-1"
			/>
		</div>
		<input
			type="text"
			bind:value={yearInput}
			onkeydown={handleSearchKeydown}
			placeholder="Year"
			class="field-control w-28"
		/>
		<input
			type="text"
			bind:value={imdbInput}
			onkeydown={handleSearchKeydown}
			placeholder="IMDb ID (tt...)"
			class="field-control w-48"
		/>
		<button
			type="button"
			onclick={handleSearch}
			disabled={search.searching || (!query.trim() && !imdbInput.trim())}
			class="btn btn-primary"
		>
			{search.searching ? 'Searching...' : 'Search'}
		</button>
	</div>

	{#if search.error}
		{#if search.error.toLowerCase().includes('api key')}
			<div class="alert alert-warning">
				<p class="title-search-alert-title">{search.error}</p>
				<p class="mt-1 title-search-alert-hint">
					Configure API keys in <a href="/settings" class="title-search-alert-link">Settings</a>.
				</p>
			</div>
		{:else}
			<div class="flex items-center gap-3">
				<p class="field-help">{search.error}</p>
			</div>
		{/if}
	{/if}

	{#if results.length > 0}
		<MatchPicker
			{results}
			query={query.trim()}
			year={yearInput.trim()}
			{providerLabel}
			canUse={$isAdmin}
			useLabel={canResolve ? 'Use this match' : 'Use poster'}
			{applying}
			onclose={closeResults}
			onselect={handlePickerSelect}
			onuse={applyResult}
		>
			{#snippet children(current: MetadataCandidate)}
				{#if $isAdmin}
					<button
						type="button"
						class="title-search-edit-toggle"
						aria-expanded={editing}
						onclick={() => toggleEdit(current)}
					>
						Edit before using
					</button>
					{#if editing}
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
								<input
									type="text"
									bind:value={editPosterUrl}
									oninput={() => (posterEdited = true)}
									placeholder="https://..."
								/>
							</label>
						</div>
					{/if}
				{/if}
				{#if feedback && feedback.row === selectedIndex && feedback.list === listGen}
					<span in:reveal class="title-search-feedback" data-tone={feedback.type}>{feedback.message}</span>
				{/if}
			{/snippet}
		</MatchPicker>
	{/if}
</div>

<style>
	/* source picker joined to the title box as one control */
	.title-search-query > input {
		min-width: 0;
		margin-left: -1px;
		border-top-left-radius: 0;
		border-bottom-left-radius: 0;
	}
	.title-search-min {
		min-width: 200px;
	}
	.title-search-alert-title {
		font-weight: 500;
	}
	.title-search-alert-link {
		text-decoration: underline;
	}
	.title-search-alert-link:hover {
		text-decoration: none;
	}
	.title-search-alert-hint {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-on-warning-soft);
	}
	.title-search-feedback {
		font-size: 0.75rem;
		line-height: 1rem;
	}
	.title-search-feedback[data-tone='success'] {
		color: var(--color-success);
	}
	.title-search-feedback[data-tone='error'] {
		color: var(--color-danger);
	}
	.title-search-edit-toggle {
		align-self: flex-start;
		font-size: 0.75rem;
		color: var(--color-primary-text);
		text-decoration: underline;
	}
</style>
