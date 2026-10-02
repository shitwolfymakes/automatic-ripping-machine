<script lang="ts">
	// The Match Episodes tab (design spec 2026-10-02 section 4): which source
	// placed this disc's tracks, how sure it was, and the per-track placement.
	import { MediaQuery } from 'svelte/reactivity';
	import type { IdentityView, JobView, TrackView } from '$lib/types/api.gen';
	import { fetchIdentity } from '$lib/api/identity';
	import { fetchNamingPreview } from '$lib/api/jobs';
	import { isAdmin } from '$lib/stores/auth';
	import { panelState, buildRows, placedCount, activeSource, failedSources, SOURCE_LABEL } from './episodeModel';
	import EpisodeRows from './EpisodeRows.svelte';

	interface Props {
		job: JobView;
		tracks: TrackView[];
		matching?: boolean;
		onsearchseries?: () => void;
	}
	let { job, tracks, matching = false, onsearchseries }: Props = $props();

	const STATUS_WORD: Record<string, string> = { ok: 'matched', miss: 'no match', skipped: 'skipped', error: 'failed' };

	let identity = $state<IdentityView | null>(null);
	let fileNames = $state(new Map<string, { name: string; path: string }>());
	let othersOpen = $state(false);
	let loadError = $state<string | null>(null);
	const phoneQuery = new MediaQuery('(max-width: 639px)', false);

	export async function reload(): Promise<void> {
		if (!job.has_series) return;
		const jobId = job.id;
		try {
			identity = await fetchIdentity(jobId);
			loadError = null;
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'Could not load episodes';
		}
		try {
			const preview = await fetchNamingPreview(jobId);
			fileNames = new Map((preview.items ?? []).map((i) => [i.track_id, { name: i.output_name, path: i.output_path }]));
		} catch {
			/* file names are a nicety */
		}
	}

	$effect(() => {
		void job.id;
		void job.has_series;
		reload();
	});

	const view = $derived(panelState(job, identity, matching));
	const rows = $derived(view === 'noseries' ? [] : buildRows(tracks, identity ?? {}, null));
	const source = $derived(identity ? activeSource(identity) : null);
	const sourceLabel = $derived(source ? (SOURCE_LABEL[source] ?? source) : null);
	const others = $derived(
		Object.entries(identity?.sources ?? {}).filter(([id]) => id.startsWith('episodes_') && id !== source)
	);
	const failed = $derived(identity ? failedSources(identity) : []);
	const showRows = $derived(view !== 'noseries' && view !== 'unavailable');
</script>

<section class="episode-panel" aria-label="Match episodes">
	{#if view === 'noseries'}
		<div class="episode-panel-noseries">
			<p class="episode-panel-noseries-title">Pick the series first</p>
			<p class="episode-panel-text">
				This job is TV, but it has no series identity, so there are no episode lists to match against.
			</p>
			{#if $isAdmin}
				<button type="button" class="btn btn-primary" onclick={() => onsearchseries?.()}>
					Search for the series
				</button>
			{/if}
		</div>
	{:else}
		<div class="episode-panel-status" role="status">
			<span class="eyebrow">Episodes</span>
			{#if view === 'matching'}
				<span class="episode-panel-text">Matching episodes…</span>
			{:else}
				{#if sourceLabel}<span class="chip chip-sm chip-info">{sourceLabel}</span>{/if}
				{#if view === 'applied'}
					<span class="chip chip-sm chip-success">Applied automatically</span>
				{:else if view === 'suggestion'}
					<span class="chip chip-sm chip-warning">Suggestion, not applied</span>
				{:else if view === 'pinned'}
					<span class="chip chip-sm chip-info">Pinned by you</span>
				{:else if view === 'nomatch'}
					<span class="chip chip-sm">No match</span>
				{/if}
				{#if showRows}
					<span class="episode-panel-count">{placedCount(rows)} of {rows.length} tracks placed</span>
				{/if}
			{/if}
			<span class="episode-panel-status-actions">
				{#if others.length > 0 && view !== 'matching'}
					<button
						type="button"
						class="btn btn-ghost btn-sm"
						aria-expanded={othersOpen}
						onclick={() => (othersOpen = !othersOpen)}
					>
						Other sources ▾
					</button>
				{/if}
			</span>
		</div>

		{#if view === 'matching'}
			<div class="progress progress-sm">
				<div data-progress-track data-indeterminate="true" class="progress-track">
					<div data-progress-fill class="progress-fill"></div>
				</div>
			</div>
		{/if}

		{#if othersOpen && others.length > 0 && view !== 'matching'}
			<ul class="episode-panel-others">
				{#each others as [id, s] (id)}
					<li>
						{SOURCE_LABEL[id] ?? id}: {STATUS_WORD[s?.status ?? 'ok'] ?? s?.status}{s?.detail ? ` · ${s.detail}` : ''}
					</li>
				{/each}
			</ul>
		{/if}

		{#if loadError}
			<div class="alert alert-danger">
				<p class="alert-title">Could not load the episode match</p>
				<p class="alert-body">{loadError}</p>
			</div>
		{:else if view === 'unavailable'}
			<div class="alert alert-warning">
				<p class="alert-title">No episode source is set up</p>
				<p class="alert-body">
					ARM needs an episode list from TMDb, TVmaze or TVDB to place these tracks. Turn one on in
					<a href="/settings#metadata">Settings › Metadata › TV episodes</a>.
				</p>
			</div>
		{:else if view === 'suggestion'}
			<div class="alert alert-warning">
				<p class="alert-title">{sourceLabel}'s best match is too uncertain to apply on its own</p>
				<p class="alert-body">The placement below is a suggestion. Nothing is applied until you accept it.</p>
			</div>
		{:else if view === 'pinned'}
			<div class="alert alert-info">
				<p class="alert-title">{sourceLabel} is pinned.</p>
				<p class="alert-body">ARM uses its placement and won't switch to another source on its own.</p>
			</div>
		{:else if view === 'nomatch'}
			<div class="alert alert-info">
				<p class="alert-title">No source could place these tracks</p>
				{#each failed as f (f.id)}
					<p class="alert-body">{f.label} failed{f.detail ? `: ${f.detail}` : ''}</p>
				{/each}
				<p class="alert-body">Try another source, season or disc number, or set the tracks by hand.</p>
			</div>
		{/if}

		{#if showRows}
			<EpisodeRows {rows} {fileNames} matching={view === 'matching'} phone={phoneQuery.current} />
		{/if}
	{/if}

	{#if !$isAdmin}
		<p class="episode-panel-guest">View only. Sign in as an admin to change episodes.</p>
	{/if}
</section>

<style>
	.episode-panel {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		min-width: 0;
	}
	.episode-panel-status {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
	}
	.episode-panel-status-actions {
		display: flex;
		gap: 0.5rem;
		margin-left: auto;
	}
	.episode-panel-count,
	.episode-panel-text {
		font-size: 0.875rem;
		color: var(--color-text-secondary);
	}
	.episode-panel-others {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem 1rem;
		padding: 0.5rem 0.75rem;
		border-radius: var(--radius-md);
		background: var(--color-primary-tint-1);
		font-size: 0.8125rem;
		color: var(--color-text-secondary);
	}
	.episode-panel-noseries {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 0.5rem;
		padding: 1rem;
		border: 1px dashed var(--color-border-strong);
		border-radius: var(--radius-lg);
	}
	.episode-panel-noseries-title {
		font-weight: 600;
		color: var(--color-text);
	}
	.episode-panel-guest {
		font-size: 0.8125rem;
		color: var(--color-text-muted);
	}
</style>
