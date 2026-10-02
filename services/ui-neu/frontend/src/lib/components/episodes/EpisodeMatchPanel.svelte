<script lang="ts">
	// The Match Episodes tab (design spec 2026-10-02 section 4): which source
	// placed this disc's tracks, how sure it was, and the per-track placement.
	import { MediaQuery } from 'svelte/reactivity';
	import type {
		EpisodeSummary,
		IdentityView,
		JobView,
		MatchPreview,
		MatchRequest,
		TrackView
	} from '$lib/types/api.gen';
	import { fetchEpisodes, fetchIdentity, matchIdentity, unpinIdentity, type EpisodeSource } from '$lib/api/identity';
	import { fetchNamingPreview, updateTrack } from '$lib/api/jobs';
	import { isAdmin } from '$lib/stores/auth';
	import {
		panelState,
		buildRows,
		placedCount,
		activeSource,
		failedSources,
		SOURCE_LABEL,
		type RerunForm
	} from './episodeModel';
	import EpisodeRows from './EpisodeRows.svelte';
	import RerunPanel from './RerunPanel.svelte';

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

	const EPISODE_SOURCES: EpisodeSource[] = ['tmdb', 'tvmaze', 'tvdb'];
	let rerunOpen = $state(false);
	let rerun = $state<RerunForm>({ source: 'tmdb', season: 1, disc: 1, tolerance: null });
	let preview = $state<MatchPreview | null>(null);
	let previewSource = $state<EpisodeSource | null>(null);
	let busy = $state(false);
	let actionError = $state<string | null>(null);
	let lastRequest = $state.raw<MatchRequest | null>(null);
	let unpinAsk = $state(false);
	let unpinError = $state<string | null>(null);
	let episodes = $state<EpisodeSummary[]>([]);
	let episodesKey = '';
	let handError = $state<string | null>(null);
	const ROLES = ['extra', 'trailer', 'other'] as const;
	const REVERT = ['role', 'season', 'episode_number', 'episode_number_end', 'episode_name'] as const;

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
	const rows = $derived(view === 'noseries' ? [] : buildRows(tracks, identity ?? {}, preview));
	const source = $derived(identity ? activeSource(identity) : null);
	const sourceLabel = $derived(source ? (SOURCE_LABEL[source] ?? source) : null);
	const others = $derived(
		Object.entries(identity?.sources ?? {}).filter(([id]) => id.startsWith('episodes_') && id !== source)
	);
	const failed = $derived(identity ? failedSources(identity) : []);
	const showRows = $derived(view !== 'noseries' && view !== 'unavailable');
	const canAct = $derived($isAdmin && view !== 'noseries' && view !== 'matching' && view !== 'unavailable');
	const sourceOptions = $derived(
		EPISODE_SOURCES.map((id) => {
			const s = identity?.sources?.[`episodes_${id}`];
			const off = s?.status === 'skipped' && /not configured/i.test(s?.detail ?? '');
			return { id, label: SOURCE_LABEL[`episodes_${id}`], disabled: off };
		})
	);
	const labelOf = (id: string | null | undefined) => SOURCE_LABEL[`episodes_${id}`] ?? id ?? '';
	const shortId = (id: string | null) => (id ?? '').replace(/^episodes_/, '') as EpisodeSource;

	function openRerun() {
		rerunOpen = !rerunOpen;
		if (!rerunOpen) return;
		const current = source ? shortId(source) : null;
		const first = sourceOptions.find((o) => !o.disabled)?.id ?? 'tmdb';
		rerun = {
			source: current && EPISODE_SOURCES.includes(current) ? current : first,
			season: job.season ?? 1,
			disc: job.disc_number ?? 1,
			tolerance: null
		};
		dropPreview();
	}

	function dropPreview() {
		preview = null;
		previewSource = null;
		actionError = null;
	}

	function request(apply: boolean): MatchRequest {
		const req: MatchRequest = { source: rerun.source, season: rerun.season, disc_number: rerun.disc, apply };
		if (rerun.tolerance != null) req.tolerance = rerun.tolerance;
		return req;
	}

	async function run(req: MatchRequest) {
		busy = true;
		actionError = null;
		lastRequest = req;
		const label = labelOf(req.source);
		try {
			const out = await matchIdentity(job.id, req);
			const failed = out.outcomes?.find((o) => o.status === 'error');
			if (failed) throw new Error(failed.detail ?? 'error');
			if (req.apply) {
				dropPreview();
				rerunOpen = false;
				await reload();
			} else {
				preview = out;
				previewSource = req.source ?? null;
			}
		} catch (e) {
			const still = sourceLabel
				? ` the placement below is still ${sourceLabel}'s.`
				: ' the placement below is unchanged.';
			actionError = `${label} didn't answer (${e instanceof Error ? e.message : 'error'}). Nothing changed;${still}`;
		} finally {
			busy = false;
		}
	}

	// The episode list behind the per-row picker: the active source's, else the
	// first source that ran and could answer (a nomatch disc still gets a list).
	const pickerSource = $derived.by((): EpisodeSource | null => {
		if (source) return shortId(source);
		const ran = sourceOptions.find((o) => {
			const st = identity?.sources?.[`episodes_${o.id}`]?.status;
			return st === 'ok' || st === 'miss';
		});
		return ran?.id ?? null;
	});

	$effect(() => {
		const src = pickerSource;
		const season = job.season ?? 1;
		const key = `${job.id}:${src}:${season}`;
		if (!src || !canAct || key === episodesKey) return;
		episodesKey = key;
		fetchEpisodes(job.id, src, season).then(
			(r) => (episodes = r.episodes ?? []),
			() => (episodes = [])
		);
	});

	const pad = (n: number) => String(n).padStart(2, '0');
	const pickOptions = $derived.by(() => {
		const season = job.season ?? 1;
		const eps = episodes.map((e) => {
			const mins = e.runtime_s != null ? ` · ${Math.round(e.runtime_s / 60)}m` : '';
			return e.special
				? { value: `s0e${e.number}`, label: `S00E${pad(e.number)} ${e.name ?? ''}${mins} · special` }
				: { value: `s${season}e${e.number}`, label: `E${pad(e.number)} ${e.name ?? ''}${mins}` };
		});
		return [...eps, ...ROLES.map((r) => ({ value: r, label: r[0].toUpperCase() + r.slice(1) }))];
	});

	async function saveTrack(trackId: string, data: Parameters<typeof updateTrack>[2]) {
		handError = null;
		try {
			await updateTrack(job.id, trackId, data);
		} catch (e) {
			handError = e instanceof Error ? e.message : 'Could not save';
			return;
		}
		await reload();
	}

	function setByHand(trackId: string, value: string) {
		const role = ROLES.find((r) => r === value);
		if (role) return saveTrack(trackId, { role });
		const m = /^s(\d+)e(\d+)$/.exec(value);
		if (!m) return;
		const [season, n] = [Number(m[1]), Number(m[2])];
		const ep = episodes.find((e) => e.number === n && !!e.special === (season === 0));
		return saveTrack(trackId, { role: 'episode', season, episode_number: n, episode_name: ep?.name ?? null });
	}

	function revert(trackId: string) {
		return saveTrack(trackId, { revert_fields: [...REVERT] });
	}

	function accept() {
		return run({ source: shortId(source), apply: true });
	}

	async function unpin() {
		unpinError = null;
		try {
			identity = await unpinIdentity(job.id);
			unpinAsk = false;
		} catch (e) {
			unpinError = e instanceof Error ? e.message : 'Could not unpin';
		}
	}
</script>

{#snippet errorAlert()}
	{#if actionError}
		<div class="alert alert-danger episode-panel-error" role="alert">
			<p class="alert-body">{actionError}</p>
			<button type="button" class="btn btn-sm" disabled={busy} onclick={() => lastRequest && run(lastRequest)}
				>Try again</button
			>
		</div>
	{/if}
{/snippet}

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
				{#if canAct}
					<button type="button" class="btn btn-sm" aria-expanded={rerunOpen} onclick={openRerun}>Re-run…</button>
				{/if}
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
				{#if canAct}
					<div class="episode-panel-banner-actions">
						<button type="button" class="btn btn-primary btn-sm" disabled={busy} onclick={accept}>
							{busy && lastRequest?.apply && !rerunOpen ? 'Accepting…' : 'Accept suggestion'}
						</button>
					</div>
				{/if}
			</div>
		{:else if view === 'pinned'}
			<div class="alert alert-info">
				<p class="alert-title">{sourceLabel} is pinned.</p>
				<p class="alert-body">ARM uses its placement and won't switch to another source on its own.</p>
				{#if canAct}
					<div class="episode-panel-banner-actions">
						{#if unpinAsk}
							<span class="alert-body">Unpin and let ARM pick the source again?</span>
							<button type="button" class="btn btn-primary btn-sm" onclick={unpin}>Unpin</button>
							<button type="button" class="btn btn-ghost btn-sm" onclick={() => (unpinAsk = false)}>Cancel</button>
						{:else}
							<button type="button" class="btn btn-sm" onclick={() => (unpinAsk = true)}>Unpin…</button>
						{/if}
					</div>
					{#if unpinError}<p class="field-error">Could not unpin: {unpinError}</p>{/if}
				{/if}
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

		{#if canAct && rerunOpen}
			<RerunPanel
				bind:form={rerun}
				sources={sourceOptions}
				{busy}
				preview={preview && previewSource
					? { changed: rows.filter((r) => r.changed).length, label: labelOf(previewSource) }
					: null}
				onfieldchange={dropPreview}
				onpreview={() => run(request(false))}
				ondiscard={dropPreview}
				onapply={() => run(request(true))}
			>
				{@render errorAlert()}
			</RerunPanel>
		{:else}
			{@render errorAlert()}
		{/if}

		{#if showRows}
			<EpisodeRows
				{rows}
				{fileNames}
				matching={view === 'matching'}
				phone={phoneQuery.current}
				proposedLabel={preview && previewSource ? labelOf(previewSource) : null}
				options={canAct && !preview ? pickOptions : null}
				onpick={setByHand}
				onrevert={revert}
			/>
			{#if handError}<p class="field-error" role="alert">Could not save the track: {handError}</p>{/if}
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
	.episode-panel-banner-actions {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		margin-top: 0.5rem;
	}
	.episode-panel-error {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		justify-content: space-between;
	}
	.episode-panel-guest {
		font-size: 0.8125rem;
		color: var(--color-text-muted);
	}
</style>
