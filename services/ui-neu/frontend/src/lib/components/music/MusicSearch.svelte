<script lang="ts">
	import { errorMessage } from '$lib/utils/errors';
	import type { JobView, TrackView, MetadataCandidate, MetadataReleaseDetail } from '$lib/types/api.gen';
	import { searchMusicMetadata, fetchMusicDetail } from '$lib/api/jobs';
	import { matchIndicator } from '$lib/jobs/track-match';
	import { musicReleaseBody } from '$lib/jobs/resolve';
	import type { MusicSearchOpts } from '$lib/music/search';
	import { visibleTracksFor, discTotalSeconds, releaseTotalMs, pairTracks, releasePatchBody } from '$lib/music/release';
	import { MusicFlipCards } from '$lib/stores/music-flip-cards.svelte';
	import { MusicReleaseApply } from '$lib/stores/music-release-apply.svelte';
	import { MusicReleaseFields } from '$lib/stores/music-release-fields.svelte';
	import MusicReleaseDetail from './music-search/MusicReleaseDetail.svelte';
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
			searchError = errorMessage(e, 'Search failed');
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
			release.feedback = { type: 'error', message: errorMessage(e, 'Load failed') };
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
		<MusicReleaseDetail
			{detail}
			{discTracks}
			tracks={visibleTracks}
			pairs={trackMapping}
			{mbTotalMs}
			{discTotalSec}
			{fields}
			{release}
			onback={() => (detail = null)}
			onapply={applyRelease}
		/>
	{/if}
</div>

<style>
	.music-search-meta {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-muted);
	}
</style>
