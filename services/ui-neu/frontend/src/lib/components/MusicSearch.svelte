<script lang="ts">
	import type { JobView, TrackView, MetadataCandidate, MetadataReleaseDetail } from '$lib/types/api.gen';
	import { searchMusicMetadata, fetchMusicDetail } from '$lib/api/jobs';
	import { MATCH_TONE, matchIndicator } from '$lib/utils/track-match';
	import { musicReleaseBody } from '$lib/utils/job-resolve';
	import { formatMinSec } from '$lib/utils/format';
	import type { MusicSearchOpts } from '$lib/utils/music-search';
	import {
		visibleTracksFor,
		discTotalSeconds,
		releaseTotalMs,
		pairTracks,
		releasePatchBody
	} from '$lib/utils/music-release';
	import PosterImage from './PosterImage.svelte';
	import { isAdmin } from '$lib/stores/auth';
	import { MusicFlipCards } from '$lib/stores/musicFlipCards.svelte';
	import { MusicReleaseApply } from '$lib/stores/musicReleaseApply.svelte';
	import { MusicReleaseFields } from '$lib/stores/musicReleaseFields.svelte';
	import Glyph from './Glyph.svelte';
	import MatchGlyph from './music-search/MatchGlyph.svelte';
	import MusicSearchForm from './music-search/MusicSearchForm.svelte';
	import MusicResultCard from './music-search/MusicResultCard.svelte';

	interface Props {
		job: JobView;
		discTracks: TrackView[];
		onapply?: () => void;
	}
	let { job, discTracks, onapply }: Props = $props();

	let searching = $state(false);
	let results = $state<MetadataCandidate[]>([]);
	let searchError = $state<string | null>(null);

	let detail = $state<MetadataReleaseDetail | null>(null);
	let loadingDetail = $state(false);

	// Cards flipped to show their tracklist on the back face.
	const flips = new MusicFlipCards();
	const fields = new MusicReleaseFields(job);

	const release = new MusicReleaseApply();

	$effect(() => {
		release.reset();
		if (detail) fields.seed(detail);
	});

	let visibleTracks = $derived(visibleTracksFor(detail, job.disc_number));

	async function handleSearch(q: string, opts: MusicSearchOpts) {
		searching = true;
		results = [];
		searchError = null;
		detail = null;
		flips.clear();
		try {
			const resp = await searchMusicMetadata(q, opts);
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
		release.feedback = null;
		try {
			detail = await fetchMusicDetail(c.provider_id);
		} catch (e) {
			release.feedback = { type: 'error', message: e instanceof Error ? e.message : 'Load failed' };
		} finally {
			loadingDetail = false;
		}
	}

	let discTotalSec = $derived(discTotalSeconds(discTracks));
	let mbTotalMs = $derived(releaseTotalMs(visibleTracks));

	let audioDiscTracks = $derived(discTracks.filter((t) => t.kind === 'audio_track'));
	let trackMapping = $derived(pairTracks(audioDiscTracks, visibleTracks));

	async function applyRelease() {
		if (!fields.album.trim() || !detail) return;
		return release.apply(
			{
				jobId: job.id,
				totalMismatch: discTracks.length > 0 && matchIndicator(mbTotalMs, discTotalSec) === 'mismatch',
				needsMapping: audioDiscTracks.length > 0 && visibleTracks.length > 0,
				resolveBody: musicReleaseBody(fields, visibleTracks),
				// Persist the release cover + any track-title mappings in one PATCH so
				// the cover art shows on the job's cards/rows (resolve doesn't set it).
				// The body is built after the resolve, from whatever release is open
				// then (#595).
				patchBody: () => releasePatchBody(detail!.poster_url ?? null, trackMapping)
			},
			onapply
		);
	}
</script>

<div class="stack">
	<MusicSearchForm {job} discTrackCount={discTracks.length} {searching} onsearch={handleSearch} />

	{#if searchError}
		<p class="music-search-meta">{searchError}</p>
	{/if}

	<!-- Results grid -->
	{#if !detail && results.length > 0}
		<div class="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
			{#each results as c, i (i)}
				{@const flipKey = c.provider_id ?? ''}
				{@const flipData = flips.get(flipKey)}
				{@const isFlipped = flips.isFlipped(flipKey)}
				<MusicResultCard
					candidate={c}
					{flipData}
					flipped={isFlipped}
					{discTracks}
					onopen={() => openDetail(c)}
					onflip={() => flips.toggle(c)}
				/>
			{/each}
		</div>
	{/if}

	<!-- Detail / apply -->
	{#if loadingDetail}
		<p class="music-search-meta">Loading...</p>
	{:else if detail}
		<div class="stack panel-section">
			<button
				onclick={() => (detail = null)}
				class="btn music-search-action-btn inline-flex items-center gap-1 self-start"
				><Glyph name="arrow-left" /> Back to results</button
			>
			<div class="flex items-start gap-3">
				<PosterImage url={detail.poster_url} class="h-24 w-24 music-search-detail-poster" />
				<div class="min-w-0 music-search-detail-meta">
					<p class="music-search-detail-title">{detail.title}</p>
					<p>{detail.artist ?? ''}</p>
					<p class="mt-1 flex flex-wrap gap-2">
						{#if detail.country}<span>{detail.country}</span>{/if}
						{#if detail.format}<span>{detail.format}</span>{/if}
						{#if detail.status}<span>{detail.status}</span>{/if}
						{#if detail.disc_count && detail.disc_count > 1}<span>{detail.disc_count} discs</span>{/if}
					</p>
					<p class="mt-0.5 mono music-search-catalog">
						{#if detail.catalog_number}Cat# {detail.catalog_number}{/if}
						{#if detail.barcode}| {detail.barcode}{/if}
					</p>
				</div>
			</div>

			<!-- Tracklist with match indicators -->
			<div class="overflow-x-auto music-search-table-scroll">
				<table class="table music-search-detail-table">
					<thead>
						<tr
							><th class="table-header">#</th><th class="table-header">Title</th>{#if discTracks.length > 0}<th
									class="table-header music-search-right">Disc Length</th
								>{/if}<th class="table-header music-search-right"
								>{discTracks.length > 0 ? 'Match Length' : 'Duration'}</th
							>{#if discTracks.length > 0}<th class="table-header music-search-center">Match</th>{/if}</tr
						>
					</thead>
					<tbody>
						{#each visibleTracks as t, i (i)}
							{@const kind = matchIndicator(t.length_ms, discTracks[i]?.expected_duration_seconds)}
							<tr class="table-row">
								<td class="table-cell">{t.position ?? i + 1}</td>
								<td class="table-cell">{t.title}</td>
								{#if discTracks.length > 0}<td class="table-cell mono music-search-right music-search-muted"
										>{formatMinSec(discTracks[i]?.expected_duration_seconds, 1)}</td
									>{/if}
								<td class="table-cell music-search-right">{formatMinSec(t.length_ms, 1000)}</td>
								{#if discTracks.length > 0}<td
										class="table-cell music-search-match"
										data-tone={MATCH_TONE[kind]}
										title={kind}><MatchGlyph {kind} /></td
									>{/if}
							</tr>
						{/each}
					</tbody>
					{#if discTracks.length > 0}
						{@const totalKind = matchIndicator(mbTotalMs, discTotalSec)}
						<tfoot class="music-search-tfoot">
							<tr>
								<td class="table-cell">Total</td>
								<td class="table-cell"></td>
								<td class="table-cell mono music-search-right">{formatMinSec(discTotalSec, 1)}</td>
								<td class="table-cell mono music-search-right">{formatMinSec(mbTotalMs, 1000)}</td>
								<td class="table-cell music-search-match" data-tone={MATCH_TONE[totalKind]} title={totalKind}
									><MatchGlyph kind={totalKind} /></td
								>
							</tr>
						</tfoot>
					{/if}
				</table>
			</div>

			<!-- Editable fields -->
			<div class="grid grid-cols-2 gap-2">
				<label class="field col-span-2"
					><span class="field-label music-search-field-label-sm">Album</span><input bind:value={fields.album} /></label
				>
				<label class="field"
					><span class="field-label music-search-field-label-sm">Artist</span><input
						bind:value={fields.artist}
					/></label
				>
				<label class="field"
					><span class="field-label music-search-field-label-sm">Year</span><input bind:value={fields.year} /></label
				>
				<label class="field"
					><span class="field-label music-search-field-label-sm">Disc #</span><input
						bind:value={fields.discNumber}
						placeholder="-"
					/></label
				>
				<label class="field"
					><span class="field-label music-search-field-label-sm">Disc total</span><input
						bind:value={fields.discTotal}
						placeholder="-"
					/></label
				>
			</div>

			{#if release.confirmMismatch}
				<div class="flex flex-wrap items-center gap-2 alert alert-danger">
					<span class="flex flex-1 items-center gap-1"
						><Glyph name="warning" /> Total length differs, likely the wrong release</span
					>
					<button
						onclick={() => {
							release.acceptMismatch();
							applyRelease();
						}}
						class="btn music-search-solid-danger music-search-action-btn"
					>
						Apply anyway
					</button>
					<button onclick={() => (release.confirmMismatch = false)} class="btn btn-ghost music-search-action-btn">
						Cancel
					</button>
				</div>
			{/if}

			{#if release.mappingPreview}
				<div class="stack panel-section music-search-mapping-preview">
					<p class="music-search-mapping-title">Confirm track title mapping</p>
					<div class="overflow-x-auto music-search-table-scroll">
						<table class="table">
							<tbody>
								{#each trackMapping as p, i (i)}
									<tr class="table-row">
										<td class="table-cell whitespace-nowrap mono music-search-muted"
											>Disc #{p.disc.index} ({formatMinSec(p.disc.expected_duration_seconds, 1)})</td
										>
										<td class="table-cell music-search-center music-search-faint"
											><Glyph name="arrow-right" class="mx-auto h-3.5 w-3.5" /></td
										>
										<td class="table-cell">{p.mb.title}</td>
										<td class="table-cell music-search-right mono music-search-muted"
											>{formatMinSec(p.mb.length_ms, 1000)}</td
										>
										<td class="table-cell music-search-match" data-tone={MATCH_TONE[p.match]} title={p.match}
											><MatchGlyph kind={p.match} /></td
										>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
					<div class="flex items-center gap-2">
						<button
							onclick={() => {
								release.acceptMapping();
								applyRelease();
							}}
							class="btn music-search-success-btn music-search-action-btn"
						>
							Apply titles
						</button>
						<button onclick={() => (release.mappingPreview = false)} class="btn btn-ghost music-search-action-btn">
							Cancel
						</button>
					</div>
				</div>
			{/if}

			<div class="flex items-center gap-2">
				{#if $isAdmin}
					<button
						onclick={applyRelease}
						disabled={release.applying || !fields.album.trim()}
						class="btn music-search-success-btn music-search-action-btn"
					>
						{release.applying ? 'Applying...' : 'Apply'}
					</button>
				{/if}
				{#if release.feedback}
					<span class="music-search-feedback" data-tone={release.feedback.type}>{release.feedback.message}</span>
				{/if}
			</div>
		</div>
	{/if}
</div>

<style>
	.music-search-right {
		text-align: right;
	}
	.music-search-meta {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-muted);
	}

	.music-search-match {
		text-align: center;
	}
	.music-search-match[data-tone='success'] {
		color: var(--color-success);
	}
	.music-search-match[data-tone='warning'] {
		color: var(--color-on-warning-soft);
	}
	.music-search-match[data-tone='danger'] {
		color: var(--color-danger);
	}
	.music-search-match[data-tone='muted'] {
		color: var(--color-text-faint);
	}

	/* :global: forwarded through PosterImage's class prop */
	:global(.music-search-detail-poster) {
		border-radius: var(--radius-md);
		object-fit: cover;
	}
	.music-search-detail-meta {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-muted);
	}
	.music-search-detail-title {
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.music-search-catalog {
		font-size: 10px;
	}
	.music-search-table-scroll {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
	}
	.music-search-detail-table {
		font-size: 0.75rem;
		line-height: 1rem;
	}
	.music-search-detail-table .table-header,
	.music-search-detail-table .table-cell {
		padding: 0.25rem 0.5rem;
	}
	.music-search-center {
		text-align: center;
	}
	.music-search-muted {
		color: var(--color-text-muted);
	}
	.music-search-faint {
		color: var(--color-text-faint);
	}
	.music-search-tfoot {
		border-top: 1px solid var(--color-border);
		background: var(--color-surface-raised);
		font-weight: 500;
	}
	.music-search-field-label-sm {
		font-size: 10px;
	}
	.music-search-solid-danger {
		border: 0;
		background: var(--color-danger);
		color: var(--color-on-primary);
	}
	.music-search-mapping-preview {
		border-color: color-mix(in srgb, var(--color-primary) 30%, transparent);
	}
	.music-search-mapping-title {
		font-weight: 500;
		color: var(--color-text-secondary);
	}
	.music-search-success-btn {
		border: 0;
		background: var(--color-success);
		color: var(--color-on-primary);
	}
	.music-search-success-btn:hover {
		filter: brightness(0.9);
	}
	/* the original action buttons were px-3 py-1.5 (0.75rem/0.375rem),
	   narrower than .btn's default */
	.music-search-action-btn {
		padding: 0.375rem 0.75rem;
		border: 0;
	}
	.music-search-feedback {
		font-size: 0.75rem;
		line-height: 1rem;
	}
	.music-search-feedback[data-tone='success'] {
		color: var(--color-success);
	}
	.music-search-feedback[data-tone='error'] {
		color: var(--color-danger);
	}
</style>
