<script lang="ts">
	import { scanFolder, createFolderJob, scanIso, createIsoJob } from '$lib/api/import-jobs';
	import type { IsoScanResult, FolderScanResult, FolderCreateRequest } from '$lib/api/import-jobs';
	import { searchMetadata, fetchMediaDetail } from '$lib/api/jobs';
	import IngressBrowser from '$lib/components/IngressBrowser.svelte';

	// Local metadata shapes the (dormant) wizard reads. v3's metadata search
	// returns a candidate envelope; this screen is feature-flagged OFF, so the
	// adapters below just satisfy the type-checker.
	interface SearchResult {
		title: string;
		year: string;
		media_type?: string;
		imdb_id?: string | null;
		poster_url?: string | null;
	}
	type MediaDetail = SearchResult;

	import PosterImage from './PosterImage.svelte';

	interface Props {
		open: boolean;
		onclose: () => void;
		oncreated: () => void;
	}

	let { open, onclose, oncreated }: Props = $props();

	// Wizard state
	let step = $state(1);
	let selectedPath = $state('');
	let selectedKind = $state<'dir' | 'iso'>('dir');
	let scanning = $state(false);
	let scanError = $state<string | null>(null);
	// Unified scan result: holds either FolderScanResult or IsoScanResult.
	// We keep it loose because callers branch on selectedKind to read fields.
	let scanResult = $state<FolderScanResult | IsoScanResult | null>(null);

	// Step 2 editable fields
	let editTitle = $state('');
	let editYear = $state('');
	let editType = $state<'movie' | 'series'>('movie');
	let editImdbId = $state('');
	let editPosterUrl = $state('');
	let editSeason = $state('');
	let editDiscNumber = $state('');
	let editDiscTotal = $state('');

	// Search state
	let searchQuery = $state('');
	let searching = $state(false);
	let searchResults = $state<SearchResult[]>([]);
	let searchError = $state<string | null>(null);
	let loadingDetail = $state(false);
	let detail = $state<MediaDetail | null>(null);

	// Step 3
	let importing = $state(false);
	let importError = $state<string | null>(null);

	function formatSize(bytes: number): string {
		if (bytes === 0) return '0 B';
		const units = ['B', 'KB', 'MB', 'GB', 'TB'];
		const i = Math.floor(Math.log(bytes) / Math.log(1024));
		return `${(bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
	}

	function reset() {
		step = 1;
		selectedPath = '';
		selectedKind = 'dir';
		scanning = false;
		scanError = null;
		scanResult = null;
		editTitle = '';
		editYear = '';
		editType = 'movie';
		editImdbId = '';
		editPosterUrl = '';
		searchQuery = '';
		searching = false;
		searchResults = [];
		searchError = null;
		loadingDetail = false;
		detail = null;
		importing = false;
		importError = null;
	}

	function handleClose() {
		reset();
		onclose();
	}

	function handleSelect(selection: { path: string; kind: 'dir' | 'iso' }) {
		selectedPath = selection.path;
		selectedKind = selection.kind;
	}

	// Convenience accessors for fields that differ between FolderScanResult and IsoScanResult.
	function scanFolderSize(r: FolderScanResult | IsoScanResult | null): number {
		if (!r) return 0;
		if ('iso_size' in r && typeof r.iso_size === 'number') return r.iso_size;
		if ('folder_size_bytes' in r && typeof r.folder_size_bytes === 'number') return r.folder_size_bytes;
		return 0;
	}

	function scanVolumeId(r: FolderScanResult | IsoScanResult | null): string | null {
		if (!r) return null;
		if ('volume_id' in r) return (r as IsoScanResult).volume_id ?? null;
		return null;
	}

	async function goToStep2() {
		if (!selectedPath) return;
		scanning = true;
		scanError = null;
		try {
			const result = selectedKind === 'iso'
				? await scanIso(selectedPath)
				: await scanFolder(selectedPath);
			scanResult = result;
			editTitle = result.title_suggestion ?? '';
			editYear = result.year_suggestion || '';
			editType = 'movie';
			editImdbId = '';
			editPosterUrl = '';
			// Folder-only fields (season/disc) only exist on FolderScanResult.
			if (selectedKind === 'dir' && 'season' in result) {
				const folderResult = result as FolderScanResult;
				editSeason = folderResult.season?.toString() || '';
				editDiscNumber = folderResult.disc_number?.toString() || '';
				editDiscTotal = folderResult.disc_total?.toString() || '';
			} else {
				editSeason = '';
				editDiscNumber = '';
				editDiscTotal = '';
			}
			searchQuery = result.title_suggestion ?? '';
			searchResults = [];
			searchError = null;
			detail = null;
			step = 2;
		} catch (e) {
			scanError = e instanceof Error ? e.message : 'Scan failed';
		} finally {
			scanning = false;
		}
	}

	async function handleSearch() {
		if (!searchQuery.trim()) return;
		searching = true;
		searchError = null;
		searchResults = [];
		detail = null;
		try {
			const resp = await searchMetadata(searchQuery.trim());
			searchResults = resp.candidates.map((c) => ({
				title: c.title,
				year: c.year != null ? String(c.year) : '',
				media_type: c.kind,
				imdb_id: c.provider_id ?? null,
				poster_url: c.poster_url ?? null
			}));
			if (searchResults.length === 0) {
				searchError = 'No results found.';
			}
		} catch (e) {
			searchError = e instanceof Error ? e.message : 'Search failed';
		} finally {
			searching = false;
		}
	}

	async function goToOmdbStep() {
		// Re-seed the search with the current title so a user who edited
		// the metadata on step 2 lands on results matching that edit.
		searchQuery = editTitle.trim() || searchQuery;
		step = 3;
		if (searchResults.length === 0 && !searching && searchQuery.trim()) {
			await handleSearch();
		}
	}

	async function handleSelectResult(result: SearchResult) {
		if (result.imdb_id) {
			loadingDetail = true;
			try {
				const lookup = await fetchMediaDetail(result.imdb_id);
				const cand = lookup.candidates[0];
				if (!cand) throw new Error('No detail');
				detail = {
					title: cand.title,
					year: cand.year != null ? String(cand.year) : '',
					media_type: cand.kind,
					imdb_id: cand.provider_id ?? null,
					poster_url: cand.poster_url ?? null
				};
				editTitle = detail.title;
				editYear = detail.year;
				editType = detail.media_type === 'series' ? 'series' : 'movie';
				editImdbId = detail.imdb_id ?? '';
				editPosterUrl = detail.poster_url ?? '';
			} catch {
				// Fall back to search result
				editTitle = result.title;
				editYear = result.year;
				editType = result.media_type === 'series' ? 'series' : 'movie';
				editImdbId = result.imdb_id ?? '';
				editPosterUrl = result.poster_url ?? '';
			} finally {
				loadingDetail = false;
			}
		} else {
			editTitle = result.title;
			editYear = result.year;
			editType = result.media_type === 'series' ? 'series' : 'movie';
			editPosterUrl = result.poster_url ?? '';
		}
	}

	function handleSearchKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') handleSearch();
	}

	async function handleImport() {
		if (!scanResult) return;
		importing = true;
		importError = null;
		try {
			const common = {
				source_path: selectedPath,
				title: editTitle.trim(),
				year: editYear.trim() || null,
				video_type: editType,
				disctype: scanResult.disc_type ?? '',
				imdb_id: editImdbId.trim() || null,
				poster_url: editPosterUrl.trim() || null,
				season: editSeason ? Number(editSeason) : null,
				disc_number: editDiscNumber ? Number(editDiscNumber) : null,
				disc_total: editDiscTotal ? Number(editDiscTotal) : null,
			};
			if (selectedKind === 'iso') {
				await createIsoJob(common);
			} else {
				await createFolderJob(common as FolderCreateRequest);
			}
			reset();
			oncreated();
		} catch (e) {
			importError = e instanceof Error ? e.message : 'Import failed';
		} finally {
			importing = false;
		}
	}
</script>

{#if open}
	<div class="modal import-wizard-modal">
		<!-- Backdrop -->
		<button
			type="button"
			class="modal-backdrop import-wizard-backdrop"
			aria-label="Close dialog"
			onclick={handleClose}
		></button>

		<!-- Dialog -->
		<div class="modal-panel modal-wide import-wizard-panel">
			<!-- Header -->
			<div class="flex items-center justify-between import-wizard-header">
				<h3 class="modal-title">Import</h3>
				<button
					type="button"
					onclick={handleClose}
					class="btn btn-icon"
					aria-label="Close"
				>
					<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>

			<!-- Body -->
			<div class="flex min-h-0 flex-1 flex-col import-wizard-body">
				{#if step === 1}
					<!-- Step 1: Pick Source -->
					{#if scanError}
						<div class="mb-2 shrink-0 alert alert-danger import-wizard-scan-error">
							{scanError}
						</div>
					{/if}
					<IngressBrowser onselect={handleSelect} />

				{:else if step === 2}
					<!-- Step 2: Verify metadata -->
					{#if scanResult}
						<div class="min-h-0 flex-1 overflow-y-auto">
							<!-- Source block header -->
							<h4 class="eyebrow import-wizard-source-title">Source</h4>
							<!-- Scan info badges -->
							<div class="flex flex-wrap gap-3 import-wizard-scan-info">
								<span class="import-wizard-disc-type">
									{(scanResult.disc_type ?? 'unknown').toUpperCase()}
								</span>
								<span class="import-wizard-muted">{formatSize(scanFolderSize(scanResult))}</span>
								<span class="import-wizard-muted">{scanResult.stream_count} streams</span>
								<span class="import-wizard-muted">Label: {scanResult.label}</span>
								{#if selectedKind === 'iso' && scanVolumeId(scanResult)}
									<span class="w-full import-wizard-volume-id">Volume ID: <span class="mono">{scanVolumeId(scanResult)}</span></span>
								{/if}
							</div>

							<!-- Poster preview + editable fields -->
							<div class="flex gap-4">
								{#if editPosterUrl}
									<PosterImage
										url={editPosterUrl}
										alt={editTitle}
										class="import-wizard-poster shrink-0"
									/>
								{:else}
									<div class="flex shrink-0 items-center justify-center import-wizard-poster-placeholder">
										<svg class="h-8 w-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
										</svg>
									</div>
								{/if}
								<div class="grid flex-1 grid-cols-2 gap-3">
									<label class="field col-span-2">
										<span class="field-label import-wizard-field-label">Title</span>
										<input type="text" bind:value={editTitle} />
									</label>
									<label class="field">
										<span class="field-label import-wizard-field-label">Year</span>
										<input type="text" bind:value={editYear} />
									</label>
									<label class="field">
										<span class="field-label import-wizard-field-label">Type</span>
										<select bind:value={editType}>
											<option value="movie">Movie</option>
											<option value="series">Series</option>
										</select>
									</label>
									<label class="field col-span-2">
										<span class="field-label import-wizard-field-label">IMDb ID</span>
										<input type="text" bind:value={editImdbId} placeholder="tt..." />
									</label>
									<label class="field">
										<span class="field-label import-wizard-field-label">Season</span>
										<input type="number" bind:value={editSeason} min="1" placeholder="-" />
									</label>
									<label class="field">
										<span class="field-label import-wizard-field-label">Disc</span>
										<div class="flex items-center gap-1">
											<input type="number" bind:value={editDiscNumber} min="1" placeholder="-" />
											<span class="import-wizard-disc-of">of</span>
											<input type="number" bind:value={editDiscTotal} min="1" placeholder="-" />
										</div>
									</label>
								</div>
							</div>
						</div>
					{/if}

				{:else if step === 3}
					<!-- Step 3: OMDB Match -->
					<div class="flex min-h-0 flex-1 flex-col">
						<div class="shrink-0 stack import-wizard-search-header">
							<p class="import-wizard-muted">
								Search OMDB to refine the auto-detected metadata. Selecting a result fills in the title, year, type, IMDb ID, and poster.
							</p>
							<div class="flex gap-2">
								<input
									type="text"
									bind:value={searchQuery}
									onkeydown={handleSearchKeydown}
									placeholder="Search title..."
									class="field-control flex-1"
								/>
								<button
									type="button"
									onclick={handleSearch}
									disabled={searching || !searchQuery.trim()}
									class="btn btn-primary"
								>
									{searching ? 'Searching...' : 'Search'}
								</button>
							</div>

							{#if searchError}
								<p class="import-wizard-muted">{searchError}</p>
							{/if}

							{#if loadingDetail}
								<p class="import-wizard-faint">Loading details...</p>
							{/if}
						</div>

						<div class="min-h-0 flex-1 overflow-y-auto">
							{#if searchResults.length > 0}
								<div class="grid grid-cols-3 gap-2 sm:grid-cols-4">
									{#each searchResults as result}
										<button
											type="button"
											onclick={() => handleSelectResult(result)}
											class="flex flex-col overflow-hidden import-wizard-result-card"
											data-selected={result.imdb_id != null && result.imdb_id === editImdbId}
										>
											{#if result.poster_url}
												<PosterImage
													url={result.poster_url}
													alt={result.title}
													class="import-wizard-result-poster w-full"
												/>
											{:else}
												<div class="flex w-full items-center justify-center import-wizard-result-poster-placeholder">
													<svg class="h-8 w-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
														<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
													</svg>
												</div>
											{/if}
											<div class="import-wizard-result-body">
												<p class="line-clamp-2 import-wizard-result-title">{result.title}</p>
												<span class="import-wizard-result-year">{result.year}</span>
											</div>
										</button>
									{/each}
								</div>
							{/if}
						</div>
					</div>

				{:else if step === 4}
					<!-- Step 4: Confirm -->
					<!-- Pinned: summary card -->
					<div class="shrink-0 panel import-wizard-summary">
						<div class="flex gap-4">
							{#if editPosterUrl}
								<PosterImage
									url={editPosterUrl}
									alt={editTitle}
									class="import-wizard-summary-poster shrink-0"
								/>
							{:else}
								<div class="flex shrink-0 items-center justify-center import-wizard-summary-poster-placeholder">
									<svg class="h-10 w-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
									</svg>
								</div>
							{/if}
							<div class="stack stack-sm import-wizard-summary-info">
								<h4 class="import-wizard-summary-title">{editTitle}</h4>
								{#if editYear}
									<p class="import-wizard-muted">{editYear}</p>
								{/if}
								<div class="flex flex-wrap gap-2">
									<span class="import-wizard-type-badge">
										{editType}
									</span>
									{#if scanResult}
										<span class="import-wizard-disc-type">
											{(scanResult.disc_type ?? 'unknown').toUpperCase()}
										</span>
									{/if}
								</div>
								{#if editImdbId}
									<p class="import-wizard-faint">IMDb: {editImdbId}</p>
								{/if}
							</div>
						</div>
					</div>

					<!-- Scrollable: source path + errors -->
					<div class="min-h-0 flex-1 overflow-y-auto import-wizard-confirm-scroll">
						<div class="stack import-wizard-confirm-source import-wizard-muted">
							<div class="flex items-center gap-2">
								<svg class="h-4 w-4 shrink-0 import-wizard-faint-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
								</svg>
								<span>Source: <span class="import-wizard-source-path">{selectedPath}</span></span>
							</div>
							{#if editSeason}
								<p>Season {editSeason}{#if editDiscNumber}, Disc {editDiscNumber}{#if editDiscTotal} of {editDiscTotal}{/if}{/if}</p>
							{/if}
						</div>
						{#if importError}
							<div class="mt-3 alert alert-danger import-wizard-scan-error">
								{importError}
							</div>
						{/if}
					</div>
				{/if}
			</div>

			<!-- Footer -->
			<div class="flex items-center justify-between import-wizard-footer">
				<div class="w-20">
					{#if step > 1}
						<button
							type="button"
							onclick={() => step--}
							class="btn btn-link"
						>
							Back
						</button>
					{/if}
				</div>
				<!-- Progress dots -->
				<div class="flex items-center gap-2">
					{#each [1, 2, 3, 4] as s}
						<div
							class="import-wizard-dot"
							data-state={s === step ? 'current' : s < step ? 'done' : 'pending'}
						></div>
					{/each}
				</div>
				<div class="flex justify-end gap-2">
					{#if step === 1}
						<button
							type="button"
							onclick={goToStep2}
							disabled={!selectedPath || scanning}
							class="btn btn-primary"
						>
							{scanning ? 'Scanning...' : 'Next'}
						</button>
					{:else if step === 2}
						<button
							type="button"
							onclick={goToOmdbStep}
							disabled={!editTitle.trim()}
							class="btn"
						>
							Search OMDB
						</button>
						<button
							type="button"
							onclick={() => step = 4}
							disabled={!editTitle.trim()}
							class="btn btn-primary"
						>
							Looks good
						</button>
					{:else if step === 3}
						<button
							type="button"
							onclick={() => step = 4}
							disabled={!editTitle.trim()}
							class="btn btn-primary"
						>
							Next
						</button>
					{:else if step === 4}
						<button
							type="button"
							onclick={handleImport}
							disabled={importing}
							class="btn btn-primary"
						>
							{importing ? 'Importing...' : 'Import'}
						</button>
					{/if}
				</div>
			</div>
		</div>
	</div>
{/if}

<style>
	/* modal-wide is 48rem; original was sm:max-w-2xl (42rem) - narrower,
	   and full-height on mobile (h-full) vs a capped 75vh from sm: up */
	.import-wizard-modal { align-items: flex-end; }
	@media (min-width: 640px) { .import-wizard-modal { align-items: center; justify-content: center; } }
	.import-wizard-backdrop { position: absolute; inset: 0; }
	.import-wizard-panel { display: flex; height: 100%; width: 100%; max-width: 42rem; flex-direction: column; padding: 0; }
	@media (min-width: 640px) { .import-wizard-panel { height: 75vh; border-radius: var(--radius-lg); } }
	.import-wizard-header { border-bottom: 1px solid var(--color-border); padding: 0.75rem 1.5rem; }
	.import-wizard-body { padding: 1rem 1.5rem; }
	.import-wizard-muted { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	.import-wizard-faint { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-faint); }
	.import-wizard-source-title { margin-bottom: 0.5rem; }
	.import-wizard-scan-info { margin-bottom: 0.75rem; font-size: 0.875rem; line-height: 1.25rem; }
	.import-wizard-disc-type { border-radius: var(--radius-sm); padding: 0.125rem 0.5rem; font-weight: 500; background: var(--color-info-soft); color: var(--color-on-info-soft); }
	.import-wizard-volume-id { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
	/* :global: forwarded through PosterImage's class prop */
	:global(.import-wizard-poster) { height: 9rem; width: 6rem; border-radius: var(--radius-md); object-fit: cover; }
	.import-wizard-poster-placeholder { height: 9rem; width: 6rem; border-radius: var(--radius-md); background: var(--color-primary-tint-2); color: var(--color-text-faint); }
	.import-wizard-field-label { margin-bottom: 0.25rem; }
	.import-wizard-disc-of { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-faint); }
	/* original was space-y-3 (0.75rem), between stack-sm's 0.5rem and
	   stack's 1rem defaults */
	.import-wizard-search-header { gap: 0.75rem; padding-bottom: 0.75rem; }
	.import-wizard-result-card { border: 1px solid var(--color-border); border-radius: var(--radius-lg); text-align: left; transition: border-color var(--motion-fast) var(--ease); }
	.import-wizard-result-card:hover { border-color: var(--color-border-strong); }
	.import-wizard-result-card[data-selected="true"] { border-color: var(--color-primary); box-shadow: 0 0 0 2px var(--color-primary); }
	/* :global: forwarded through PosterImage's class prop */
	:global(.import-wizard-result-poster) { aspect-ratio: 2 / 3; object-fit: cover; }
	.import-wizard-result-poster-placeholder { aspect-ratio: 2 / 3; background: var(--color-primary-tint-2); color: var(--color-text-faint); }
	.import-wizard-result-body { padding: 0.375rem; }
	.import-wizard-result-title { font-size: 0.75rem; line-height: 1rem; font-weight: 500; color: var(--color-text); }
	.import-wizard-result-year { font-size: 10px; color: var(--color-text-muted); }
	.import-wizard-summary { padding: 1rem; }
	/* :global: forwarded through PosterImage's class prop */
	:global(.import-wizard-summary-poster) { height: 10rem; width: 7rem; border-radius: var(--radius-md); object-fit: cover; }
	.import-wizard-summary-poster-placeholder { height: 10rem; width: 7rem; border-radius: var(--radius-md); background: var(--color-primary-tint-2); color: var(--color-text-faint); }
	.import-wizard-summary-info { font-size: 0.875rem; line-height: 1.25rem; }
	.import-wizard-summary-title { font-size: 1.125rem; line-height: 1.75rem; font-weight: 600; color: var(--color-text); }
	.import-wizard-type-badge { border-radius: var(--radius-sm); padding: 0.125rem 0.5rem; font-size: 0.75rem; line-height: 1rem; font-weight: 500; background: var(--color-success-soft); color: var(--color-on-success-soft); }
	.import-wizard-confirm-scroll { padding-top: 1rem; }
	/* original was space-y-3 (0.75rem) */
	.import-wizard-confirm-source { gap: 0.75rem; }
	.import-wizard-faint-icon { color: var(--color-text-faint); }
	.import-wizard-source-path { font-weight: 500; color: var(--color-text-secondary); }
	.import-wizard-footer { border-top: 1px solid var(--color-border); padding: 0.75rem 1.5rem; }
	.import-wizard-dot { height: 0.5rem; width: 0.5rem; border-radius: 9999px; background: var(--color-border-strong); transition: background-color var(--motion-fast) var(--ease); }
	.import-wizard-dot[data-state="current"] { background: var(--color-primary); }
	.import-wizard-dot[data-state="done"] { background: color-mix(in srgb, var(--color-primary) 50%, transparent); }
	/* both scan/import error boxes were p-3 (0.75rem all sides), not .alert's
	   own 0.5rem/0.75rem default */
	.import-wizard-scan-error { padding: 0.75rem; }
</style>
