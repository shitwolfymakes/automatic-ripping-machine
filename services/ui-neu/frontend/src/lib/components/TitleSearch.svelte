<script lang="ts">
	import type { ExternalIds, JobView, MetadataCandidate, ResolveResponse } from '$lib/types/api.gen';
	import { searchMetadata, fetchMediaDetail, updateJobTitle, resolveJob, type MatchProvider } from '$lib/api/jobs';
	import MatchPicker from './match/MatchPicker.svelte';
	import { isSeriesKind } from '$lib/utils/match';
	import { reveal } from '$lib/transitions';
	import { isAdmin } from '$lib/stores/auth';
	import { searchProviders, keyedSources } from '$lib/stores/config';

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
	type Source = 'tmdb' | 'omdb' | 'tvmaze' | 'tvdb';
	const SOURCES: Record<'movie' | 'tv', { id: Source; label: string }[]> = {
		movie: [
			{ id: 'tmdb', label: 'TMDb' },
			{ id: 'omdb', label: 'OMDb' }
		],
		tv: [
			{ id: 'tmdb', label: 'TMDb' },
			{ id: 'omdb', label: 'OMDb' },
			{ id: 'tvmaze', label: 'TVmaze' },
			{ id: 'tvdb', label: 'TVDB' }
		]
	};
	let pickedSource = $state<Source | null>(null);
	let sourceOptions = $derived(SOURCES[searchType]);
	let source = $derived.by<Source | undefined>(() => {
		if (pickedSource && sourceOptions.some((o) => o.id === pickedSource)) return pickedSource;
		const fromSettings = searchType === 'tv' ? $searchProviders.tv : $searchProviders.movie;
		const settingsSource = sourceOptions.find((o) => o.id === fromSettings)?.id;
		// The default's key was removed after it was chosen: start on the first
		// usable source; with none usable keep the default (the backend's 400 shows).
		if (settingsSource && !sourceKeyed(settingsSource)) {
			return sourceOptions.find((o) => sourceKeyed(o.id))?.id ?? settingsSource;
		}
		return settingsSource;
	});

	function sourceKeyed(id: Source): boolean {
		return id === 'tvmaze' || $keyedSources[id];
	}

	// The job's type changed (Movie/TV switch): the old pick and results belong
	// to the other type.
	let lastSearchType: 'movie' | 'tv' | undefined;
	$effect(() => {
		const t = searchType;
		if (lastSearchType !== undefined && t !== lastSearchType) {
			pickedSource = null;
			closeResults();
			searchError = null;
		}
		lastSearchType = t;
	});

	let query = $state(job.title || '');
	let yearInput = $state(job.year != null ? String(job.year) : '');
	let imdbInput = $state('');
	let searching = $state(false);
	let results = $state<MetadataCandidate[]>([]);
	let searchError = $state<string | null>(null);

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

	async function handleSearch() {
		const imdb = imdbInput.trim();
		if (imdb) {
			// Direct IMDb ID lookup — skip search
			searching = true;
			searchError = null;
			closeResults();
			try {
				const resp = await fetchMediaDetail(imdb);
				results = resp.candidates.slice(0, 1);
				if (!results.length) searchError = 'No match found for that IMDb ID.';
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
		closeResults();
		try {
			const resp = await searchMetadata(query.trim(), searchType, source, parsedSearchYear);
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

	async function applyResult(c: MetadataCandidate) {
		const at = { row: selectedIndex, list: listGen };
		const values = editing
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
		const parsedYear = values.year ? Number(values.year) : null;
		const year = Number.isFinite(parsedYear as number) ? parsedYear : null;
		const mediaType = values.isSeries ? 'tv' : 'movie';
		// The candidate's ids name a title of its own kind; after a type edit they don't apply.
		const idsApply = isSeriesKind(c.kind) === values.isSeries;
		let resolved: ResolveResponse | undefined;
		try {
			if (canResolve && idsApply && c.provider) {
				// A picked match states the whole show (spec 3.6): every show id,
				// nulls included, plus provider, poster and facts in one call.
				const ids = c.external_ids ?? {};
				const externalIds: ExternalIds = {
					imdb: ids.imdb ?? null,
					tmdb: ids.tmdb ?? null,
					tmdb_kind: ids.tmdb_kind ?? null,
					tvdb: ids.tvdb ?? null,
					tvmaze: ids.tvmaze ?? null
				};
				resolved = await resolveJob(job.id, {
					title: values.title,
					year,
					media_type: mediaType,
					external_ids: externalIds,
					match: {
						provider: c.provider as MatchProvider,
						// The candidate's own poster stays the automatic one; an edit is the override.
						poster_url: c.poster_url ?? null,
						poster_is_manual: editing && posterEdited,
						poster_url_manual: editing && posterEdited ? values.poster : null,
						facts: c.facts ?? null
					}
				});
				feedback = { type: 'success', message: 'Identified', ...at };
			} else if (canResolve) {
				resolved = await resolveJob(job.id, { title: values.title, year, media_type: mediaType });
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
			<select
				aria-label="Search with"
				value={source}
				onchange={(e) => (pickedSource = (e.target as HTMLSelectElement).value as Source)}
				class="field-control title-search-source"
			>
				{#each sourceOptions as opt (opt.id)}
					{@const keyed = sourceKeyed(opt.id)}
					<option value={opt.id} disabled={!keyed}>{keyed ? opt.label : `${opt.label} (needs API key)`}</option>
				{/each}
			</select>
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
			disabled={searching || (!query.trim() && !imdbInput.trim())}
			class="btn btn-primary"
		>
			{searching ? 'Searching...' : 'Search'}
		</button>
	</div>

	{#if searchError}
		{#if searchError.toLowerCase().includes('api key')}
			<div class="alert alert-warning">
				<p class="title-search-alert-title">{searchError}</p>
				<p class="mt-1 title-search-alert-hint">
					Configure API keys in <a href="/settings" class="title-search-alert-link">Settings</a>.
				</p>
			</div>
		{:else}
			<div class="flex items-center gap-3">
				<p class="field-help">{searchError}</p>
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
	.title-search-source {
		width: auto;
		flex: none;
		border-top-right-radius: 0;
		border-bottom-right-radius: 0;
		background: var(--color-primary-tint-2);
	}
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
