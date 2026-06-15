<script lang="ts">
	import type { JobView, TrackView, MetadataCandidate, MetadataReleaseDetail } from '$lib/types/api.gen';
	import { searchMusicMetadata, fetchMusicDetail, updateJobTitle } from '$lib/api/jobs';
	import { posterSrc, posterFallback } from '$lib/utils/poster';

	interface Props {
		job: JobView;
		// Accepted for caller compatibility; v3's music-detail contract no longer
		// exposes per-track durations, so disc-track duration matching is gone.
		discTracks?: TrackView[];
		onapply?: () => void;
	}

	// eslint-disable-next-line @typescript-eslint/no-unused-vars
	let { job, discTracks = [], onapply }: Props = $props();

	let query = $state(job.title || '');
	let searching = $state(false);
	let results = $state<MetadataCandidate[]>([]);
	let searchError = $state<string | null>(null);

	let selectedId = $state<string | null>(null);
	let detail = $state<MetadataReleaseDetail | null>(null);
	let loadingDetail = $state(false);

	let applying = $state(false);
	let feedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	let failedImages = $state(new Set<string>());

	// Editable metadata fields (populated from detail). v3's job edit only
	// accepts poster_url_manual; we surface the release art as the editable.
	let editPosterUrl = $state('');

	$effect(() => {
		if (detail) {
			editPosterUrl = detail.poster_url ?? '';
		}
	});

	async function handleSearch() {
		if (!query.trim()) return;
		searching = true;
		searchError = null;
		results = [];
		selectedId = null;
		detail = null;
		failedImages = new Set();
		try {
			const resp = await searchMusicMetadata(query.trim());
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

	async function handleSelect(result: MetadataCandidate) {
		const releaseId = result.provider_id;
		if (!releaseId) return;
		if (selectedId === releaseId) {
			selectedId = null;
			detail = null;
			return;
		}
		selectedId = releaseId;
		loadingDetail = true;
		detail = null;
		try {
			detail = await fetchMusicDetail(releaseId);
		} catch {
			detail = { release_id: releaseId, title: result.title, artist: null, year: result.year ?? null, poster_url: result.poster_url ?? null, tracks: [] };
		} finally {
			loadingDetail = false;
		}
	}

	async function applyPoster() {
		applying = true;
		feedback = null;
		try {
			await updateJobTitle(job.id, { poster_url_manual: editPosterUrl.trim() || null });
			feedback = { type: 'success', message: 'Poster updated' };
			onapply?.();
		} catch (e) {
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Update failed' };
		} finally {
			applying = false;
		}
	}

	function backToResults() {
		detail = null;
		selectedId = null;
	}

	function handleSearchKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') handleSearch();
	}

	function hasValidPoster(url: string | null | undefined): boolean {
		return !!url && !failedImages.has(url);
	}

	const btnBase =
		'rounded-lg px-3 py-1.5 text-sm font-medium disabled:opacity-50 transition-colors';
	const inputBase =
		'rounded-lg border border-primary/25 bg-primary/5 px-3 py-1.5 text-sm text-gray-900 focus:border-primary focus:outline-hidden focus:ring-1 focus:ring-primary dark:border-primary/30 dark:bg-primary/10 dark:text-white';
</script>

<div class="space-y-4">
	<!-- Search panel -->
	<div class="rounded-lg border border-primary/20 bg-primary/[0.02] p-3 dark:border-primary/20 dark:bg-primary/[0.03]">
		<div class="flex flex-wrap items-end gap-2">
			<label class="min-w-[160px] flex-1">
				<span class="mb-0.5 block text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">Album / Title</span>
				<input
					type="text"
					bind:value={query}
					onkeydown={handleSearchKeydown}
					onfocus={(e) => (e.target as HTMLInputElement).select()}
					placeholder="Album or title..."
					class="w-full {inputBase}"
				/>
			</label>
			<div class="flex items-center gap-2">
				<span class="mb-0.5 block text-[10px]">&nbsp;</span>
				<button
					onclick={handleSearch}
					disabled={searching || !query.trim()}
					class="{btnBase} bg-primary text-on-primary hover:bg-primary-hover dark:bg-primary dark:hover:bg-primary-hover"
				>
					{searching ? 'Searching...' : 'Search'}
				</button>
			</div>
		</div>
	</div>

	{#if searchError}
		<p class="text-sm text-gray-500 dark:text-gray-400">{searchError}</p>
	{/if}

	<!-- Results grid (hidden when detail is shown) -->
	{#if !detail && results.length > 0}
		<div class="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
			{#each results as result}
				<button
					onclick={() => handleSelect(result)}
					class="group flex w-full flex-col overflow-hidden rounded-lg border text-left transition-all {selectedId === result.provider_id
						? 'border-primary ring-2 ring-primary/30'
						: 'border-primary/20 hover:border-primary/40 dark:border-primary/20 dark:hover:border-primary/40'}"
				>
					<div class="relative aspect-square w-full">
						{#if hasValidPoster(result.poster_url)}
							<img
								src={posterSrc(result.poster_url)}
								alt={result.title}
								class="aspect-square w-full object-cover"
								loading="lazy"
								onerror={posterFallback}
							/>
						{:else}
							<div
								class="flex aspect-square w-full items-center justify-center bg-primary/10 text-gray-400 dark:bg-primary/15"
							>
								<svg class="h-10 w-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="1.5"
										d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"
									/>
								</svg>
							</div>
						{/if}
					</div>
					<div class="p-2">
						<p
							class="text-sm font-medium text-gray-900 group-hover:text-primary-text dark:text-white dark:group-hover:text-primary-text-dark line-clamp-2"
						>
							{result.title}
						</p>
						<div class="mt-1 flex flex-wrap items-center gap-1">
							{#if result.year}
								<span class="text-xs text-gray-500 dark:text-gray-400">{result.year}</span>
							{/if}
							<span class="rounded-sm bg-purple-100 px-1 py-0.5 text-[10px] font-medium text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">
								{result.kind}
							</span>
						</div>
					</div>
				</button>
			{/each}
		</div>
	{/if}

	<!-- Detail panel -->
	{#if loadingDetail}
		<div class="rounded-lg border border-primary/20 bg-page p-4 text-sm text-gray-500 dark:border-primary/20 dark:bg-page-dark dark:text-gray-400">
			Loading details...
		</div>
	{:else if detail}
		<div class="overflow-hidden rounded-lg border border-primary/20 dark:border-primary/20">
			<div class="space-y-3 p-4">
				{#if results.length > 0}
					<button
						onclick={backToResults}
						class="inline-flex items-center gap-1 text-sm text-primary hover:text-primary-hover dark:text-primary dark:hover:text-primary-hover"
					>
						<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
						</svg>
						Back to results
					</button>
				{/if}

				<!-- Album art + info summary -->
				<div class="flex gap-4">
					<div class="relative h-28 w-28 shrink-0 overflow-hidden rounded-md">
						{#if hasValidPoster(detail.poster_url)}
							<img
								src={posterSrc(detail.poster_url)}
								alt={detail.title}
								class="h-full w-full object-cover"
								onerror={posterFallback}
							/>
						{:else}
							<div
								class="flex h-full w-full items-center justify-center bg-primary/10 text-gray-400 dark:bg-primary/15"
							>
								<svg class="h-10 w-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="1.5"
										d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"
									/>
								</svg>
							</div>
						{/if}
					</div>
					<div class="min-w-0 flex-1">
						<p class="text-lg font-semibold text-gray-900 dark:text-white">{detail.title}</p>
						{#if detail.artist}
							<p class="text-sm text-gray-600 dark:text-gray-300">{detail.artist}</p>
						{/if}
						{#if detail.year}
							<p class="mt-1.5 text-xs text-gray-500 dark:text-gray-400">{detail.year}</p>
						{/if}
					</div>
				</div>

				<!-- Track listing -->
				{#if detail.tracks && detail.tracks.length > 0}
					<div>
						<h4 class="mb-2 text-sm font-semibold text-gray-700 dark:text-gray-300">Track Listing</h4>
						<div class="overflow-x-auto rounded-md border border-primary/15 dark:border-primary/20">
							<table class="w-full text-left text-xs">
								<thead class="bg-page text-gray-500 dark:bg-primary/5 dark:text-gray-400">
									<tr>
										<th class="w-10 px-3 py-1.5 font-medium">#</th>
										<th class="px-3 py-1.5 font-medium">Title</th>
									</tr>
								</thead>
								<tbody class="divide-y divide-gray-100 dark:divide-gray-700/50">
									{#each detail.tracks as track, i}
										<tr>
											<td class="px-3 py-1.5 font-mono text-gray-500 dark:text-gray-400">{track.position ?? i + 1}</td>
											<td class="px-3 py-1.5 text-gray-700 dark:text-gray-300">{track.title}</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
					</div>
				{/if}

				<!-- Editable poster -->
				<div class="grid grid-cols-1 gap-3">
					<label>
						<span class="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">Cover Art URL</span>
						<input type="text" bind:value={editPosterUrl} placeholder="https://..." class="w-full {inputBase}" />
					</label>
				</div>
				<div class="flex items-center gap-2">
					<button
						onclick={applyPoster}
						disabled={applying}
						class="{btnBase} bg-green-600 text-white hover:bg-green-700 dark:bg-green-500 dark:hover:bg-green-600"
					>
						{applying ? 'Applying...' : 'Apply Cover Art'}
					</button>
					{#if feedback}
						<span
							class="text-xs {feedback.type === 'success'
								? 'text-green-600 dark:text-green-400'
								: 'text-red-600 dark:text-red-400'}"
						>
							{feedback.message}
						</span>
					{/if}
				</div>
			</div>
		</div>
	{/if}
</div>
