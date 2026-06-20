<script lang="ts">
	import type { JobView, TrackView, MetadataCandidate, MetadataReleaseDetail } from '$lib/types/api.gen';
	import { searchMusicMetadata, fetchMusicDetail, resolveJob } from '$lib/api/jobs';
	import { matchIndicator } from '$lib/utils/track-match';
	import PosterImage from './PosterImage.svelte';

	interface Props {
		job: JobView;
		discTracks: TrackView[];
		onapply?: () => void;
	}
	let { job, discTracks, onapply }: Props = $props();

	const meta = (job.metadata_json ?? {}) as Record<string, unknown>;
	let query = $state(job.title || (typeof meta.album === 'string' ? meta.album : ''));
	let artist = $state(typeof meta.artist === 'string' ? meta.artist : '');
	let matchCount = $state(discTracks.length > 0);

	let searching = $state(false);
	let results = $state<MetadataCandidate[]>([]);
	let searchError = $state<string | null>(null);

	let detail = $state<MetadataReleaseDetail | null>(null);
	let loadingDetail = $state(false);
	let editArtist = $state('');
	let editAlbum = $state('');
	let editYear = $state('');
	let discNumber = $state(job.disc_number != null ? String(job.disc_number) : '');
	let discTotal = $state(job.disc_total != null ? String(job.disc_total) : '');

	let applying = $state(false);
	let feedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	$effect(() => {
		if (detail) {
			editArtist = detail.artist ?? '';
			editAlbum = detail.title;
			editYear = detail.year != null ? String(detail.year) : '';
			if (detail.disc_count != null && detail.disc_count > 1 && !discTotal) {
				discTotal = String(detail.disc_count);
			}
		}
	});

	// When the job knows its disc, scope a multi-disc release's tracklist to it.
	let visibleTracks = $derived(
		detail == null
			? []
			: detail.disc_count != null && detail.disc_count > 1 && job.disc_number != null
				? (detail.tracks ?? []).filter((t) => t.disc_number === job.disc_number)
				: (detail.tracks ?? [])
	);

	async function handleSearch() {
		if (!query.trim()) return;
		searching = true;
		results = [];
		searchError = null;
		detail = null;
		try {
			const opts: { artist?: string; track_count?: number } = {};
			if (artist.trim()) opts.artist = artist.trim();
			if (matchCount && discTracks.length > 0) opts.track_count = discTracks.length;
			const resp = await searchMusicMetadata(query.trim(), opts);
			results = resp.candidates;
			if (resp.detail) searchError = resp.detail;
			else if (results.length === 0) searchError = 'No results found.';
		} catch (e) {
			searchError = e instanceof Error ? e.message : 'Search failed';
		} finally {
			searching = false;
		}
	}

	async function openDetail(c: MetadataCandidate) {
		if (!c.provider_id) return;
		loadingDetail = true;
		feedback = null;
		try {
			detail = await fetchMusicDetail(c.provider_id);
		} catch (e) {
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Load failed' };
		} finally {
			loadingDetail = false;
		}
	}

	function fmtMs(ms: number | null | undefined): string {
		if (ms == null) return '—';
		const total = Math.round(ms / 1000);
		return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
	}

	const MATCH_GLYPH = { match: '✓', close: '~', mismatch: '✗', unknown: '—' };
	const MATCH_CLASS = {
		match: 'text-green-600 dark:text-green-400',
		close: 'text-amber-600 dark:text-amber-400',
		mismatch: 'text-red-600 dark:text-red-400',
		unknown: 'text-gray-400'
	};

	async function applyRelease() {
		if (!editAlbum.trim() || !detail) return;
		applying = true;
		feedback = null;
		try {
			const yr = editYear.trim() ? Number(editYear.trim()) : null;
			const dn = discNumber.trim() ? Number(discNumber.trim()) : null;
			const dt = discTotal.trim() ? Number(discTotal.trim()) : null;
			const tracks = (detail.tracks ?? []).map((t) => ({
				position: t.position,
				title: t.title,
				length_ms: t.length_ms ?? null,
				disc_number: t.disc_number ?? null
			}));
			await resolveJob(job.id, {
				title: editAlbum.trim(),
				year: Number.isFinite(yr as number) ? yr : null,
				disc_number: Number.isFinite(dn as number) ? dn : null,
				disc_total: Number.isFinite(dt as number) ? dt : null,
				metadata: { artist: editArtist.trim(), album: editAlbum.trim(), tracks }
			});
			feedback = { type: 'success', message: 'Release applied' };
			onapply?.();
		} catch (e) {
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Apply failed' };
		} finally {
			applying = false;
		}
	}

	const inputBase = 'rounded-md border border-primary/25 bg-primary/5 px-2 py-1 text-sm text-gray-900 focus:border-primary focus:outline-hidden focus:ring-1 focus:ring-primary dark:border-primary/30 dark:bg-primary/10 dark:text-white';
	const btnBase = 'rounded-md px-2 py-1 text-xs font-medium disabled:opacity-50 transition-colors';
</script>

<div class="space-y-3">
	<!-- Search form -->
	<div class="flex flex-wrap gap-1.5">
		<input type="text" bind:value={query} placeholder="Album / title..." class="min-w-[160px] flex-1 {inputBase}" />
		<input type="text" bind:value={artist} placeholder="Artist (optional)" class="min-w-[120px] flex-1 {inputBase}" />
		<button onclick={handleSearch} disabled={searching || !query.trim()} class="{btnBase} bg-primary text-on-primary hover:bg-primary-hover">
			{searching ? '...' : 'Search'}
		</button>
	</div>
	{#if discTracks.length > 0}
		<label class="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400">
			<input type="checkbox" bind:checked={matchCount} class="h-3.5 w-3.5" />
			Match track count ({discTracks.length})
		</label>
	{/if}

	{#if searchError}
		<p class="text-xs text-gray-500 dark:text-gray-400">{searchError}</p>
	{/if}

	<!-- Results grid -->
	{#if !detail && results.length > 0}
		<div class="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
			{#each results as c}
				<button onclick={() => openDetail(c)} class="group rounded-md border border-primary/15 text-left dark:border-primary/20">
					<PosterImage url={c.poster_url} class="aspect-square w-full rounded-t-md object-cover" />
					<div class="p-1.5">
						<p class="truncate text-[11px] font-medium text-gray-900 dark:text-white">{c.title}</p>
						{#if c.year}<p class="text-[10px] text-gray-500">{c.year}</p>{/if}
					</div>
				</button>
			{/each}
		</div>
	{/if}

	<!-- Detail / apply -->
	{#if loadingDetail}
		<p class="text-xs text-gray-400">Loading...</p>
	{:else if detail}
		<div class="space-y-3 rounded-md border border-primary/15 bg-primary/5 p-3 dark:border-primary/20 dark:bg-primary/10">
			<button onclick={() => (detail = null)} class="{btnBase} text-gray-500 hover:text-gray-700 dark:text-gray-400">← Back to results</button>
			<div class="flex items-start gap-3">
				<PosterImage url={detail.poster_url} class="h-24 w-24 rounded object-cover" />
				<div class="min-w-0 text-xs text-gray-600 dark:text-gray-400">
					<p class="text-sm font-semibold text-gray-900 dark:text-white">{detail.title}</p>
					<p>{detail.artist ?? ''}</p>
					<p class="mt-1 space-x-2">
						{#if detail.country}<span>{detail.country}</span>{/if}
						{#if detail.format}<span>{detail.format}</span>{/if}
						{#if detail.status}<span>{detail.status}</span>{/if}
						{#if detail.disc_count && detail.disc_count > 1}<span>{detail.disc_count} discs</span>{/if}
					</p>
					<p class="mt-0.5 font-mono text-[10px]">
						{#if detail.catalog_number}Cat# {detail.catalog_number}{/if}
						{#if detail.barcode}· {detail.barcode}{/if}
					</p>
				</div>
			</div>

			<!-- Tracklist with match indicators -->
			<div class="overflow-x-auto rounded border border-primary/15 dark:border-primary/20">
				<table class="w-full text-left text-xs">
					<thead class="bg-page text-gray-600 dark:bg-primary/5 dark:text-gray-400">
						<tr><th class="px-2 py-1">#</th><th class="px-2 py-1">Title</th><th class="px-2 py-1 text-right">Length</th>{#if discTracks.length > 0}<th class="px-2 py-1 text-center">Match</th>{/if}</tr>
					</thead>
					<tbody class="divide-y divide-gray-200 dark:divide-gray-700">
						{#each visibleTracks as t, i}
							{@const kind = matchIndicator(t.length_ms, discTracks[i]?.expected_duration_seconds)}
							<tr>
								<td class="px-2 py-1">{t.position ?? i + 1}</td>
								<td class="px-2 py-1">{t.title}</td>
								<td class="px-2 py-1 text-right">{fmtMs(t.length_ms)}</td>
								{#if discTracks.length > 0}<td class="px-2 py-1 text-center {MATCH_CLASS[kind]}" title={kind}>{MATCH_GLYPH[kind]}</td>{/if}
							</tr>
						{/each}
					</tbody>
				</table>
			</div>

			<!-- Editable fields -->
			<div class="grid grid-cols-2 gap-2">
				<label class="col-span-2"><span class="mb-0.5 block text-[10px] text-gray-500">Album</span><input bind:value={editAlbum} class="w-full {inputBase}" /></label>
				<label><span class="mb-0.5 block text-[10px] text-gray-500">Artist</span><input bind:value={editArtist} class="w-full {inputBase}" /></label>
				<label><span class="mb-0.5 block text-[10px] text-gray-500">Year</span><input bind:value={editYear} class="w-full {inputBase}" /></label>
				<label><span class="mb-0.5 block text-[10px] text-gray-500">Disc #</span><input bind:value={discNumber} placeholder="—" class="w-full {inputBase}" /></label>
				<label><span class="mb-0.5 block text-[10px] text-gray-500">Disc total</span><input bind:value={discTotal} placeholder="—" class="w-full {inputBase}" /></label>
			</div>

			<div class="flex items-center gap-2">
				<button onclick={applyRelease} disabled={applying || !editAlbum.trim()} class="{btnBase} bg-green-600 text-white hover:bg-green-700 dark:bg-green-500">
					{applying ? 'Applying...' : 'Apply'}
				</button>
				{#if feedback}
					<span class="text-xs {feedback.type === 'success' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}">{feedback.message}</span>
				{/if}
			</div>
		</div>
	{/if}
</div>
