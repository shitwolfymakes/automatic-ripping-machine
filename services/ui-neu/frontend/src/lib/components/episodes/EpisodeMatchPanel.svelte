<script lang="ts">
	// The Match Episodes tab (design spec 2026-10-02 section 4): which source
	// placed this disc's tracks, how sure it was, and the per-track placement.
	import { untrack } from 'svelte';
	import { MediaQuery } from 'svelte/reactivity';
	import type {
		EpisodeSummary,
		IdentityView,
		JobView,
		MatchPreview,
		MatchRequest,
		TrackView
	} from '$lib/types/api.gen';
	import {
		fetchEpisodes,
		fetchIdentity,
		fetchSeasons,
		matchIdentity,
		unpinIdentity,
		type EpisodeSource
	} from '$lib/api/identity';
	import { fetchNamingPreview, updateTrack } from '$lib/api/jobs';
	import { isAdmin } from '$lib/stores/auth';
	import {
		panelState,
		buildRows,
		placedCount,
		activeSource,
		failedSources,
		heldSeason,
		holdReasons,
		seasonAlternatives,
		pickerOptions,
		ROLE_OPTIONS,
		SOURCE_LABEL,
		type EpisodeRow,
		type RerunForm,
		type SeasonCandidate
	} from './episodeModel';
	import Glyph from '../Glyph.svelte';
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
	let loaded = $state(false);
	let loadedFor: string | null = null;
	const phoneQuery = new MediaQuery('(max-width: 639px)', false);

	const EPISODE_SOURCES: EpisodeSource[] = ['tmdb', 'tvmaze', 'tvdb'];
	let rerunOpen = $state(false);
	// No season or disc is assumed: unknown stays empty until the operator picks.
	const NO_RERUN: RerunForm = { source: 'tmdb', season: null, disc: null, tolerance: null };
	let rerun = $state<RerunForm>({ ...NO_RERUN });
	// The seasons of the re-run form's source while it is open, else of the
	// picker's source (the per-row season select); null when the list could not load.
	let seasons = $state<number[] | null>([]);
	let seasonsKey = '';
	let preview = $state<MatchPreview | null>(null);
	let previewSource = $state<EpisodeSource | null>(null);
	// The request that produced the preview on screen: Apply & pin sends exactly
	// it. previewSeq invalidates a preview still in flight when the form changes.
	let previewRequest: MatchRequest | null = null;
	let previewSeq = 0;
	let busy = $state(false);
	let accepting = $state(false);
	let unpinBusy = $state(false);
	let actionError = $state<string | null>(null);
	let lastRequest = $state.raw<MatchRequest | null>(null);
	let unpinAsk = $state(false);
	let unpinError = $state<string | null>(null);
	// The picker's episode lists by season, for the job and source in episodesFor.
	let episodesBySeason = $state.raw(new Map<number, EpisodeSummary[]>());
	let episodesFor = '';
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- fetch bookkeeping, never read reactively
	const episodesRequested = new Set<number>();
	// A season the operator picked for a row with no episode yet (nothing saved).
	let rowSeason = $state<Record<string, number>>({});
	let handError = $state<string | null>(null);
	const ROLES = ['extra', 'trailer', 'other'] as const;
	const REVERT = ['role', 'season', 'episode_number', 'episode_number_end', 'episode_name'] as const;

	export async function reload(): Promise<void> {
		if (!job.has_series) return;
		const jobId = job.id;
		try {
			const next = await fetchIdentity(jobId);
			if (job.id !== jobId) return;
			identity = next;
			loadError = null;
		} catch (e) {
			if (job.id !== jobId) return;
			loadError = e instanceof Error ? e.message : 'Could not load episodes';
		}
		loaded = true;
		try {
			const preview = await fetchNamingPreview(jobId);
			if (job.id !== jobId) return;
			fileNames = new Map((preview.items ?? []).map((i) => [i.track_id, { name: i.output_name, path: i.output_path }]));
		} catch {
			/* file names are a nicety */
		}
	}

	// Everything that belongs to one job is dropped when the panel is handed
	// another, so nothing (a preview, an open form, a late response) leaks across.
	function resetForJob() {
		identity = null;
		loaded = false;
		loadError = null;
		fileNames = new Map();
		othersOpen = false;
		rerunOpen = false;
		rerun = { ...NO_RERUN };
		dropPreview();
		lastRequest = null;
		unpinAsk = false;
		unpinError = null;
		seasons = [];
		seasonsKey = '';
		episodesBySeason = new Map();
		episodesFor = '';
		episodesRequested.clear();
		rowSeason = {};
		handError = null;
	}

	$effect(() => {
		const id = job.id;
		void job.has_series;
		untrack(() => {
			if (loadedFor !== null && loadedFor !== id) resetForJob();
			loadedFor = id;
			reload();
		});
	});

	$effect(() => {
		if (matching) untrack(dropPreview);
	});

	const view = $derived(panelState(job, identity, matching));
	const loading = $derived(!loaded && view !== 'noseries' && view !== 'matching');
	const rows = $derived(view === 'noseries' ? [] : buildRows(tracks, identity ?? {}, preview));
	const source = $derived(identity ? activeSource(identity) : null);
	const sourceLabel = $derived(source ? (SOURCE_LABEL[source] ?? source) : null);
	const others = $derived(
		Object.entries(identity?.sources ?? {}).filter(([id]) => id.startsWith('episodes_') && id !== source)
	);
	const failed = $derived(identity ? failedSources(identity) : []);
	const showRows = $derived(!loading && view !== 'noseries' && view !== 'unavailable');
	const canAct = $derived($isAdmin && !loading && view !== 'noseries' && view !== 'matching' && view !== 'unavailable');
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
			season: job.season ?? null,
			disc: job.disc_number ?? null,
			tolerance: null
		};
		dropPreview();
	}

	function dropPreview() {
		previewSeq++;
		previewRequest = null;
		preview = null;
		previewSource = null;
		actionError = null;
	}

	function request(apply: boolean): MatchRequest {
		const req: MatchRequest = { source: rerun.source, apply };
		if (rerun.season === 'scan') req.scan_seasons = true;
		else if (rerun.season != null) req.season = rerun.season;
		if (rerun.disc != null) req.disc_number = rerun.disc;
		if (rerun.tolerance != null) req.tolerance = rerun.tolerance;
		return req;
	}

	// Candidate seasons under the status line: the held result's own season
	// first (one click confirms it), then the other seasons the scan fit.
	const ownSeason = $derived(
		identity && canAct && view === 'suggestion' ? heldSeason(identity, source, rows.length) : null
	);
	const altSeasons = $derived(
		identity && canAct
			? seasonAlternatives(identity, source, rows.length).filter((a) => a.season !== ownSeason?.season)
			: []
	);
	const candidates = $derived<SeasonCandidate[]>(ownSeason ? [ownSeason, ...altSeasons] : altSeasons);
	const seasonName = (n: number) => (n === 0 ? 'Specials' : `Season ${n}`);

	// Preview one candidate season in the re-run form, so its Apply is at hand.
	function tryCandidate(season: number) {
		const src = pickerSource ?? rerun.source;
		rerun = { source: src, season, disc: job.disc_number ?? null, tolerance: null };
		rerunOpen = true;
		dropPreview();
		return run({ source: src, season, disc_number: job.disc_number ?? undefined, apply: false });
	}

	async function run(req: MatchRequest) {
		busy = true;
		actionError = null;
		lastRequest = req;
		const label = labelOf(req.source);
		const jobId = job.id;
		const seq = ++previewSeq;
		// A preview is stale once the form (or the job) changed while it ran.
		const stale = () => job.id !== jobId || (!req.apply && seq !== previewSeq);
		try {
			const out = await matchIdentity(jobId, req);
			if (stale()) return;
			const failed = out.outcomes?.find((o) => o.status === 'error');
			if (failed) {
				// An apply pins its source even when that source failed: reload so
				// the pinned state shows, then report the failure.
				if (req.apply) await reload();
				if (stale()) return;
				throw new Error(failed.detail ?? 'error');
			}
			if (req.apply) {
				dropPreview();
				rerunOpen = false;
				await reload();
			} else {
				preview = out;
				previewSource = req.source ?? null;
				previewRequest = req;
			}
		} catch (e) {
			if (stale()) return;
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

	// The season list follows the re-run form's source while the form is open,
	// else the picker's source. Tracked on identity so a reload retries a list
	// that failed (a loaded one is skipped by its key).
	const seasonsSource = $derived<EpisodeSource | null>(rerunOpen ? rerun.source : pickerSource);
	$effect(() => {
		const src = seasonsSource;
		const jobId = job.id;
		void identity;
		if (!src || !canAct) return;
		const key = `${jobId}:${src}`;
		if (key === seasonsKey) return;
		seasonsKey = key;
		untrack(() => (seasons = []));
		fetchSeasons(jobId, src).then(
			(r) => {
				if (seasonsKey === key) seasons = r.seasons ?? [];
			},
			() => {
				if (seasonsKey !== key) return;
				seasons = null;
				seasonsKey = '';
			}
		);
	});

	// The identity tracks that hold an episode: their saved season is the row's.
	const placed = $derived(
		new Map((identity?.tracks ?? []).filter((t) => t.episode_number != null).map((t) => [t.track_id, t] as const))
	);
	// A row's own season: one picked for it here (not saved until an episode
	// is picked), else its saved one; null when neither is set.
	const savedOrPicked = (row: EpisodeRow): number | null => rowSeason[row.trackId] ?? row.season;
	// The disc's season the rows fall back to: the re-run form's season while
	// the form is open and names one, else the job's; null when none is known.
	const discSeason = $derived(rerunOpen && typeof rerun.season === 'number' ? rerun.season : (job.season ?? null));
	// The season a row's list comes from: its own, else the disc's; null when
	// none is known (the disc's season is never assumed).
	const seasonOf = (row: EpisodeRow): number | null => savedOrPicked(row) ?? discSeason;
	// The rows as shown: each carries its own season (EpisodeRows falls back to the disc's).
	const shownRows = $derived(rows.map((r) => ({ ...r, season: savedOrPicked(r) })));

	// Every season a row shows gets its episode list, once per job and source.
	// Tracked on identity (through rows) so a reload retries a list that failed.
	$effect(() => {
		const src = pickerSource;
		const jobId = job.id;
		const needed = new Set(rows.map(seasonOf).filter((n): n is number => n != null));
		if (!src || !canAct) return;
		untrack(() => {
			const key = `${jobId}:${src}`;
			if (key !== episodesFor) {
				episodesFor = key;
				episodesRequested.clear();
				episodesBySeason = new Map();
			}
			for (const season of needed) {
				if (episodesRequested.has(season)) continue;
				episodesRequested.add(season);
				fetchEpisodes(jobId, src, season).then(
					(r) => {
						if (episodesFor !== key) return;
						// eslint-disable-next-line svelte/prefer-svelte-reactivity -- copy-on-write; reassigning the $state.raw variable triggers updates
						episodesBySeason = new Map(episodesBySeason).set(season, r.episodes ?? []);
					},
					() => {
						if (episodesFor === key) episodesRequested.delete(season);
					}
				);
			}
		});
	});

	// The episode numbers the other tracks of a season already hold.
	function usedIn(season: number, trackId: string): Set<number> {
		// eslint-disable-next-line svelte/prefer-svelte-reactivity -- a fresh value per call, never mutated after
		const used = new Set<number>();
		for (const t of placed.values()) {
			if (t.track_id === trackId || t.season !== season || t.episode_number == null) continue;
			for (let n = t.episode_number; n <= (t.episode_number_end ?? t.episode_number); n++) used.add(n);
		}
		return used;
	}

	// The by-hand choices of a shown row (its season already resolved). The
	// roles need no season; the episodes do.
	function optionsFor(row: EpisodeRow) {
		const season = row.season ?? discSeason;
		if (season == null) return ROLE_OPTIONS;
		return pickerOptions(episodesBySeason.get(season) ?? [], season, row.seconds, usedIn(season, row.trackId));
	}

	// Picking a season saves nothing: it switches the row's episode list, and
	// the season is saved with the episode picked from it.
	function setRowSeason(trackId: string, season: number) {
		rowSeason = { ...rowSeason, [trackId]: season };
	}

	function clearRowSeason(trackId: string) {
		if (!(trackId in rowSeason)) return;
		const { [trackId]: _dropped, ...rest } = rowSeason;
		rowSeason = rest;
	}

	async function saveTrack(trackId: string, data: Parameters<typeof updateTrack>[2]): Promise<boolean> {
		handError = null;
		try {
			await updateTrack(job.id, trackId, data);
		} catch (e) {
			handError = e instanceof Error ? e.message : 'Could not save';
			return false;
		}
		await reload();
		return true;
	}

	async function setByHand(trackId: string, value: string) {
		const role = ROLES.find((r) => r === value);
		if (role) return saveTrack(trackId, { role });
		const m = /^s(\d+)e(\d+)$/.exec(value);
		if (!m) return;
		const [season, n] = [Number(m[1]), Number(m[2])];
		const row = rows.find((r) => r.trackId === trackId);
		const listSeason = row ? seasonOf(row) : null;
		const list = listSeason == null ? [] : (episodesBySeason.get(listSeason) ?? []);
		const ep = list.find((e) => e.number === n && (!!e.special || listSeason === 0) === (season === 0));
		const data = { role: 'episode' as const, season, episode_number: n, episode_name: ep?.name ?? null };
		if (await saveTrack(trackId, data)) clearRowSeason(trackId);
	}

	// Fill the rest: preview the source over the tracks not set by hand (the
	// backend keeps each hand-set track and reserves its episode), shown in the
	// re-run form so its Apply is at hand. Offered once a track is set by hand
	// and another is not, however the others were placed.
	const canFill = $derived(!!pickerSource && rows.some((r) => r.handSet) && rows.some((r) => !r.handSet));
	// The season to fill in: the job's, else the one season every hand-set row
	// was saved in; null (no season sent) when they disagree or none is known.
	function fillSeason(): number | null {
		if (job.season != null) return job.season;
		const held = new Set(rows.filter((r) => r.handSet).map((r) => r.season));
		const [only] = held;
		return held.size === 1 && only != null ? only : null;
	}
	function fillTheRest() {
		const src = pickerSource;
		if (!src) return;
		const season = fillSeason();
		rerun = { source: src, season, disc: job.disc_number ?? null, tolerance: null };
		rerunOpen = true;
		dropPreview();
		const req: MatchRequest = { source: src, apply: false };
		if (season != null) req.season = season;
		if (job.disc_number != null) req.disc_number = job.disc_number;
		return run(req);
	}

	async function revert(trackId: string) {
		if (await saveTrack(trackId, { revert_fields: [...REVERT] })) clearRowSeason(trackId);
	}

	async function accept() {
		accepting = true;
		try {
			await run({ source: shortId(source), apply: true });
		} finally {
			accepting = false;
		}
	}

	function applyPreview() {
		if (previewRequest) return run({ ...previewRequest, apply: true });
	}

	async function unpin() {
		if (unpinBusy) return;
		unpinBusy = true;
		unpinError = null;
		const jobId = job.id;
		try {
			const next = await unpinIdentity(jobId);
			if (job.id !== jobId) return;
			identity = next;
			unpinAsk = false;
		} catch (e) {
			if (job.id === jobId) unpinError = e instanceof Error ? e.message : 'Could not unpin';
		} finally {
			unpinBusy = false;
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
				<span class="episode-panel-text">Matching episodes...</span>
			{:else if loading}
				<span class="episode-panel-text">Loading episodes...</span>
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
				{#if canAct && canFill && !preview}
					<button type="button" class="btn btn-sm" disabled={busy} onclick={fillTheRest}>Fill the rest</button>
				{/if}
				{#if canAct}
					<button type="button" class="btn btn-sm" aria-expanded={rerunOpen} onclick={openRerun}>Re-run...</button>
				{/if}
				{#if others.length > 0 && view !== 'matching'}
					<button
						type="button"
						class="btn btn-ghost btn-sm"
						aria-expanded={othersOpen}
						onclick={() => (othersOpen = !othersOpen)}
					>
						Other sources <Glyph name="chevron-down" />
					</button>
				{/if}
			</span>
		</div>

		{#if candidates.length > 0 && !loading && !loadError}
			<div class="episode-panel-seasons">
				{#each candidates as c, i (c.season)}
					{#if i === (ownSeason ? 1 : 0)}<span class="episode-panel-text">Also fits:</span>{/if}
					<button type="button" class="btn btn-sm" disabled={busy} onclick={() => tryCandidate(c.season)}>
						{seasonName(c.season)} ({c.matches} of {c.total} titles)
					</button>
				{/each}
			</div>
		{/if}

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
						{SOURCE_LABEL[id] ?? id}: {STATUS_WORD[s?.status ?? 'ok'] ?? s?.status}{s?.detail ? `, ${s.detail}` : ''}
					</li>
				{/each}
			</ul>
		{/if}

		{#if loading}
			<!-- first fetch still running: no state to show yet -->
		{:else if loadError}
			<div class="alert alert-danger">
				<p class="alert-title">Could not load the episode match</p>
				<p class="alert-body">{loadError}</p>
			</div>
		{:else if view === 'unavailable'}
			<div class="alert alert-warning">
				<p class="alert-title">No episode source is set up</p>
				<p class="alert-body">
					ARM needs an episode list from TMDb, TVmaze or TVDB to place these tracks. Turn one on in
					<a href="/settings#Identification/episode_sources">Settings › Identification › Identity</a>.
				</p>
			</div>
		{:else if view === 'suggestion'}
			<div class="alert alert-warning">
				<p class="alert-title">{sourceLabel}'s best match is too uncertain to apply on its own</p>
				<p class="alert-body">The placement below is a suggestion. Nothing is applied until you accept it.</p>
				{#each holdReasons(identity ?? {}, source) as reason (reason)}
					<p class="alert-body">{reason}</p>
				{/each}
				<p class="alert-body">Set the season or disc number in Info, or accept the suggestion.</p>
				{#if canAct}
					<div class="episode-panel-banner-actions">
						<button type="button" class="btn btn-primary btn-sm" disabled={busy} onclick={accept}>
							{accepting ? 'Accepting...' : 'Accept suggestion'}
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
							<button type="button" class="btn btn-primary btn-sm" disabled={unpinBusy} onclick={unpin}>Unpin</button>
							<button type="button" class="btn btn-ghost btn-sm" disabled={unpinBusy} onclick={() => (unpinAsk = false)}
								>Cancel</button
							>
						{:else}
							<button type="button" class="btn btn-sm" onclick={() => (unpinAsk = true)}>Unpin...</button>
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
				{seasons}
				{busy}
				preview={preview && previewSource
					? { changed: rows.filter((r) => r.changed).length, label: labelOf(previewSource) }
					: null}
				onfieldchange={dropPreview}
				onpreview={() => run(request(false))}
				ondiscard={dropPreview}
				onapply={applyPreview}
			>
				{@render errorAlert()}
			</RerunPanel>
		{:else}
			{@render errorAlert()}
		{/if}

		{#if showRows}
			<EpisodeRows
				rows={shownRows}
				{fileNames}
				matching={view === 'matching'}
				phone={phoneQuery.current}
				proposedLabel={preview && previewSource ? labelOf(previewSource) : null}
				optionsFor={canAct && !preview ? optionsFor : null}
				{seasons}
				panelSeason={discSeason}
				onseason={setRowSeason}
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
	.episode-panel-seasons {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
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
