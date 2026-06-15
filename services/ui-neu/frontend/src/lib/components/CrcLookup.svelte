<script lang="ts">
	import { onMount } from 'svelte';
	import type { JobView } from '$lib/types/api.gen';
	import { fetchCrcLookup, submitToCrcDb, updateJobTitle } from '$lib/api/jobs';
	import PosterImage from './PosterImage.svelte';

	// ---------------------------------------------------------------------------
	// MISSING in v3 — CRC lookup / submission have no v3 endpoint (fetchCrcLookup /
	// submitToCrcDb REJECT at runtime). This screen is feature-gated OFF; it is
	// kept type-clean only. The BFF response shapes (CrcLookupResponse /
	// CrcLookupResult) were removed from jobs.ts, so they are declared LOCALLY
	// here purely to type the now-dead state. No v3 type fits — the feature is dead.
	// ---------------------------------------------------------------------------
	interface CrcLookupResult {
		title: string;
		year: string;
		video_type?: string;
		disctype?: string;
		label?: string;
		imdb_id?: string;
		tmdb_id?: string;
		poster_url?: string;
		hasnicetitle?: string;
		validated?: string;
		date_added?: string;
	}
	interface CrcLookupResponse {
		found?: boolean;
		no_crc?: boolean;
		error?: string;
		has_api_key?: boolean;
		results?: CrcLookupResult[];
	}

	interface Props {
		job: JobView;
		// CRC / video-type metadata have no JobView equivalent (BFF-only); accept
		// them as optional props so the (dead) screen still type-checks.
		crcId?: string | null;
		videoType?: string | null;
		imdbId?: string | null;
		onapply?: () => void;
	}

	let { job, crcId = null, videoType = null, imdbId = null, onapply }: Props = $props();

	let loading = $state(true);
	let lookup = $state<CrcLookupResponse | null>(null);
	let lookupError = $state<string | null>(null);

	let submitting = $state(false);
	let submitFeedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	// Editable fields for CRC submission
	let subTitle = $state(job.title || '');
	let subYear = $state(job.year != null ? String(job.year) : '');
	let subType = $state(videoType || 'movie');
	let subImdbId = $state(imdbId || '');

	let canSubmit = $derived(subTitle.trim() !== '' && subYear.trim() !== '');

	let subDirty = $derived(
		subTitle !== (job.title || '') ||
		subYear !== (job.year != null ? String(job.year) : '') ||
		subType !== (videoType || 'movie') ||
		subImdbId !== (imdbId || '')
	);

	async function doLookup() {
		loading = true;
		lookupError = null;
		try {
			lookup = (await fetchCrcLookup(job.id)) as CrcLookupResponse;
		} catch (e) {
			lookupError = e instanceof Error ? e.message : 'Lookup failed';
		} finally {
			loading = false;
		}
	}

	async function handleSubmit() {
		submitting = true;
		submitFeedback = null;
		try {
			// Save edits to job first if changed. v3 only accepts poster_url_manual
			// on the job; title/year/type live behind identify/resolve, so the
			// edited values are silently dropped (dead screen).
			if (subDirty) {
				await updateJobTitle(job.id, {});
				onapply?.();
			}
			await submitToCrcDb(job.id);
			submitFeedback = { type: 'success', message: 'Submitted successfully' };
			await doLookup();
		} catch (e) {
			submitFeedback = { type: 'error', message: e instanceof Error ? e.message : 'Submit failed' };
		} finally {
			submitting = false;
		}
	}

	let applying = $state(false);
	let applyFeedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	async function handleApply(_result: CrcLookupResult) {
		applying = true;
		applyFeedback = null;
		try {
			// v3 only accepts poster_url_manual on the job (dead screen).
			await updateJobTitle(job.id, { poster_url_manual: _result.poster_url || null });
			applyFeedback = { type: 'success', message: 'Job updated' };
			onapply?.();
		} catch (e) {
			applyFeedback = { type: 'error', message: e instanceof Error ? e.message : 'Update failed' };
		} finally {
			applying = false;
		}
	}

	onMount(() => {
		doLookup();
	});

	const inputBase =
		'rounded-lg border border-primary/25 bg-primary/5 px-3 py-1.5 text-sm text-gray-900 focus:border-primary focus:outline-hidden focus:ring-1 focus:ring-primary dark:border-primary/30 dark:bg-primary/10 dark:text-white';

	const typeBadgeClass = (vt: string) => {
		switch (vt) {
			case 'series':
				return 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400';
			case 'movie':
				return 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400';
			default:
				return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400';
		}
	};
</script>

<div class="space-y-4">
	<!-- CRC64 hash display -->
	{#if crcId}
		<div class="flex items-center gap-2 text-sm">
			<span class="text-gray-500 dark:text-gray-400">CRC64:</span>
			<code class="rounded-sm bg-gray-100 px-2 py-0.5 font-mono text-xs text-gray-800 dark:bg-gray-800 dark:text-gray-300">{crcId}</code>
		</div>
	{/if}

	<!-- Lookup results -->
	{#if loading}
		<p class="text-sm text-gray-500 dark:text-gray-400">Looking up CRC database...</p>
	{:else if lookupError}
		<p class="text-sm text-red-600 dark:text-red-400">{lookupError}</p>
	{:else if lookup?.no_crc}
		<p class="text-sm text-gray-500 dark:text-gray-400">No CRC hash for this disc type.</p>
	{:else if lookup?.error}
		<div class="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-800 dark:bg-amber-900/20">
			<svg class="mt-0.5 h-4 w-4 shrink-0 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
			</svg>
			<p class="text-sm text-amber-700 dark:text-amber-400">{lookup.error}</p>
		</div>
	{:else if lookup && !lookup.found}
		<div class="flex items-center gap-2">
			<p class="text-sm text-gray-500 dark:text-gray-400">No matches found in the CRC database.</p>
			<button
				onclick={doLookup}
				disabled={loading}
				aria-label="Refresh CRC lookup"
				class="rounded-sm p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
			>
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
				</svg>
			</button>
		</div>
	{:else if lookup?.results}
		<div class="space-y-3">
			{#each lookup.results as result}
				<div class="rounded-lg border border-primary/20 p-4 dark:border-primary/20">
					<div class="flex gap-4">
					{#if result.poster_url}
						<PosterImage url={result.poster_url} alt={result.title} />
					{/if}
					<dl class="grid flex-1 grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
						<dt class="text-gray-500 dark:text-gray-400">Title</dt>
						<dd class="font-medium text-gray-900 dark:text-white">{result.title || 'N/A'}</dd>
						<dt class="text-gray-500 dark:text-gray-400">Year</dt>
						<dd class="text-gray-900 dark:text-white">{result.year || 'N/A'}</dd>
						<dt class="text-gray-500 dark:text-gray-400">Video Type</dt>
						<dd>
							{#if result.video_type}
								<span class="rounded-sm px-1.5 py-0.5 text-[10px] font-medium uppercase {typeBadgeClass(result.video_type)}">
									{result.video_type}
								</span>
							{:else}
								<span class="text-gray-900 dark:text-white">N/A</span>
							{/if}
						</dd>
						<dt class="text-gray-500 dark:text-gray-400">Disc Type</dt>
						<dd class="text-gray-900 dark:text-white">{result.disctype || 'N/A'}</dd>
						<dt class="text-gray-500 dark:text-gray-400">Label</dt>
						<dd class="font-mono text-xs text-gray-900 dark:text-white">{result.label && result.label !== 'None' ? result.label : 'N/A'}</dd>
						<dt class="text-gray-500 dark:text-gray-400">IMDb ID</dt>
						<dd>
							{#if result.imdb_id}
								<a
									href="https://www.imdb.com/title/{result.imdb_id}"
									target="_blank"
									rel="noopener noreferrer"
									class="text-primary-text hover:underline dark:text-primary-text-dark"
								>{result.imdb_id}</a>
							{:else}
								<span class="text-gray-900 dark:text-white">N/A</span>
							{/if}
						</dd>
						<dt class="text-gray-500 dark:text-gray-400">TMDb ID</dt>
						<dd class="text-gray-900 dark:text-white">{result.tmdb_id && result.tmdb_id !== 'None' ? result.tmdb_id : 'N/A'}</dd>
						<dt class="text-gray-500 dark:text-gray-400">Validated</dt>
						<dd class="text-gray-900 dark:text-white">{result.validated === 'True' ? 'Yes' : 'No'}</dd>
						<dt class="text-gray-500 dark:text-gray-400">Date Added</dt>
						<dd class="text-gray-900 dark:text-white">{result.date_added ? result.date_added.split('.')[0] : 'N/A'}</dd>
						<dt class="text-gray-500 dark:text-gray-400">Poster</dt>
						<dd>
							{#if result.poster_url}
								<a href={result.poster_url} target="_blank" rel="noopener noreferrer" class="break-all text-xs text-primary-text hover:underline dark:text-primary-text-dark">{result.poster_url}</a>
							{:else}
								<span class="text-gray-900 dark:text-white">N/A</span>
							{/if}
						</dd>
					</dl>
					</div>
					<div class="mt-3 flex items-center gap-2">
						<button
							onclick={() => handleApply(result)}
							disabled={applying}
							class="rounded-lg px-3 py-1.5 text-sm font-medium bg-green-600 text-white hover:bg-green-700 dark:bg-green-500 dark:hover:bg-green-600 disabled:opacity-50 transition-colors"
						>
							{applying ? 'Applying...' : 'Apply to Job'}
						</button>
						{#if applyFeedback}
							<span class="text-xs {applyFeedback.type === 'success' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}">
								{applyFeedback.message}
							</span>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	{/if}

	<!-- Submit section -->
	{#if !lookup?.no_crc && lookup?.has_api_key}
		<hr class="border-gray-200 dark:border-gray-700" />
		<div class="space-y-3">
			<h4 class="text-sm font-semibold text-gray-700 dark:text-gray-300">Submit to CRC Database</h4>
			<div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
				<label class="sm:col-span-2">
					<span class="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">Title</span>
					<input type="text" bind:value={subTitle} class="w-full {inputBase}" />
				</label>
				<label>
					<span class="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">Year</span>
					<input type="text" bind:value={subYear} class="w-full {inputBase}" />
				</label>
				<label>
					<span class="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">Type</span>
					<select bind:value={subType} class="w-full {inputBase}">
						<option value="movie">Movie</option>
						<option value="series">Series</option>
					</select>
				</label>
				<label class="sm:col-span-2">
					<span class="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">IMDb ID</span>
					<input type="text" bind:value={subImdbId} placeholder="tt..." class="w-full {inputBase}" />
				</label>
			</div>
			{#if !canSubmit}
				<p class="text-xs text-amber-600 dark:text-amber-400">Title and year are required to submit.</p>
			{/if}
			<div class="flex items-center gap-3">
				<button
					onclick={handleSubmit}
					disabled={submitting || !canSubmit}
					class="rounded-lg px-3 py-1.5 text-sm font-medium bg-primary/5 text-gray-700 ring-1 ring-primary/25 hover:bg-primary/10 dark:bg-primary/10 dark:text-gray-200 dark:ring-primary/30 dark:hover:bg-primary/15 disabled:opacity-50 transition-colors"
				>
					{submitting ? 'Submitting...' : subDirty ? 'Save & Submit' : 'Submit'}
				</button>
				{#if submitFeedback}
					<span class="text-sm {submitFeedback.type === 'success' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}">
						{submitFeedback.message}
					</span>
				{/if}
			</div>
		</div>
	{/if}
</div>
