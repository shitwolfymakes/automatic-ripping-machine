<script lang="ts">
	import { errorMessage } from '$lib/utils/errors';
	// The Match Episodes tab (design spec 2026-10-02 section 4): which source
	// placed this disc's tracks, how sure it was, and the per-track placement.
	import { untrack } from 'svelte';
	import { MediaQuery } from 'svelte/reactivity';
	import type { JobView, TrackView } from '$lib/types/api.gen';
	import { clearEpisodeMatch, type EpisodeSource } from '$lib/api/identity';
	import { updateTrack } from '$lib/api/jobs';
	import { isAdmin } from '$lib/stores/auth';
	import { EpisodeIdentity } from '$lib/stores/episode-identity.svelte';
	import { EpisodeLists } from '$lib/stores/episode-lists.svelte';
	import { MatchRunner } from '$lib/stores/match-runner.svelte';
	import { SeasonList } from '$lib/stores/season-list.svelte';
	import {
		panelState,
		buildRows,
		placedCount,
		failedSources,
		pickerOptions,
		parseHandPick,
		pickedEpisodeName,
		usedEpisodeNumbers,
		ROLE_OPTIONS,
		type EpisodeRow
	} from '../../episodes/episode-model';
	import {
		activeSource,
		episodeSourceOptions,
		pickerSourceFor,
		shortSourceLabel,
		SOURCE_LABEL
	} from '$lib/episodes/sources';
	import { heldSeason, holdHeadline, seasonAlternatives, type SeasonCandidate } from '$lib/episodes/hold';
	import { fillRestForm, fixMatchForm, rerunRequest, type RerunForm } from '$lib/jobs/rerun-form';
	import Glyph from '../Glyph.svelte';
	import EpisodeRows from './EpisodeRows.svelte';
	import EpisodeStateAlert from './EpisodeStateAlert.svelte';
	import EpisodeStatusBar from './EpisodeStatusBar.svelte';
	import RerunPanel from './RerunPanel.svelte';

	interface Props {
		job: JobView;
		tracks: TrackView[];
		matching?: boolean;
		onsearchseries?: () => void;
		/** Tracks or the match changed here: the owner reloads what it shows of them (the card's tracks table). */
		onchanged?: () => void;
	}
	let { job, tracks, matching = false, onsearchseries, onchanged }: Props = $props();
	const STATUS_WORD: Record<string, string> = { ok: 'matched', miss: 'no match', skipped: 'skipped', error: 'failed' };

	const episodeIdentity = new EpisodeIdentity(() => job.id);
	const identity = $derived(episodeIdentity.identity);
	let othersOpen = $state(false);
	// The (i) next to a held result's one-line reading: the other reasons.
	let whyOpen = $state(false);
	let loadedFor: string | null = null;
	const phoneQuery = new MediaQuery('(max-width: 639px)', false);

	let rerunOpen = $state(false);
	// No season or disc is assumed: unknown stays empty until the operator picks.
	const NO_RERUN: RerunForm = { source: 'tmdb', season: null, disc: null, tolerance: null };
	let rerun = $state<RerunForm>({ ...NO_RERUN });
	// The seasons of the re-run form's source while it is open, else of the
	// picker's source (the per-row season select); null when the list could not load.
	const seasonList = new SeasonList();
	const runner = new MatchRunner({
		jobId: () => job.id,
		placementLabel: () => sourceLabel,
		closeForm: () => (rerunOpen = false),
		reload: async () => {
			await reload();
			onchanged?.();
		}
	});
	let clearing = $state(false);
	// The picker's episode lists by season.
	const episodeLists = new EpisodeLists();
	// A season the operator picked for a row with no episode yet (nothing saved).
	let rowSeason = $state<Record<string, number>>({});
	let handError = $state<string | null>(null);
	const REVERT = ['role', 'season', 'episode_number', 'episode_number_end', 'episode_name'] as const;

	export async function reload(): Promise<void> {
		if (!job.has_series) return;
		await episodeIdentity.load(job.id);
	}

	// Everything that belongs to one job is dropped when the panel is handed
	// another, so nothing (a preview, an open form, a late response) leaks across.
	function resetForJob() {
		episodeIdentity.reset();
		othersOpen = false;
		whyOpen = false;
		rerunOpen = false;
		rerun = { ...NO_RERUN };
		runner.reset();
		seasonList.reset();
		episodeLists.reset();
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
		if (matching) untrack(runner.drop);
	});

	const view = $derived(panelState(job, identity, matching));
	const loading = $derived(!episodeIdentity.loaded && view !== 'noseries' && view !== 'matching');
	const rows = $derived(
		view === 'noseries' ? [] : buildRows(tracks, identity ?? {}, runner.preview, !!job.episodes_unsure)
	);
	const source = $derived(identity ? activeSource(identity) : null);
	const sourceLabel = $derived(source ? (SOURCE_LABEL[source] ?? source) : null);
	const others = $derived(
		Object.entries(identity?.sources ?? {}).filter(([id]) => id.startsWith('episodes_') && id !== source)
	);
	const failed = $derived(identity ? failedSources(identity) : []);
	const showRows = $derived(!loading && view !== 'noseries' && view !== 'unavailable');
	const canAct = $derived($isAdmin && !loading && view !== 'noseries' && view !== 'matching' && view !== 'unavailable');
	const sourceOptions = $derived(episodeSourceOptions(identity));

	// Fix match: the one control for changing a match. Opens the form seeded
	// with the current source and, for a guess, the season it guessed.
	function fixMatch() {
		rerunOpen = !rerunOpen;
		if (!rerunOpen) return;
		rerun = fixMatchForm(source, sourceOptions, ownSeason?.season ?? altSeasons[0]?.season ?? null, job);
		runner.drop();
	}

	// A guess: the season the source guessed and the other seasons the scan
	// fit, shown as facts under the status line; Fix match opens the form on
	// the guessed season.
	const ownSeason = $derived(identity && view === 'unsure' ? heldSeason(identity, source, rows.length) : null);
	const altSeasons = $derived<SeasonCandidate[]>(
		identity && view === 'unsure'
			? seasonAlternatives(identity, source, rows.length).filter((a) => a.season !== ownSeason?.season)
			: []
	);
	const seasonName = (n: number) => (n === 0 ? 'Specials' : `Season ${n}`);
	const fitText = (c: SeasonCandidate) => `${seasonName(c.season)} (${c.matches} of ${c.total} titles)`;
	const alsoFits = $derived(altSeasons.map(fitText).join(', '));
	const held = $derived(
		identity && view === 'unsure' ? holdHeadline(identity, source, ownSeason?.season ?? null) : null
	);
	// Clear episodes: forget the match so the placements come off the tracks.
	// Hand-set tracks keep theirs; Fix match brings a match back.
	async function clearEpisodes() {
		if (clearing) return;
		clearing = true;
		runner.error = null;
		const jobId = job.id;
		try {
			const next = await clearEpisodeMatch(jobId);
			if (job.id !== jobId) return;
			episodeIdentity.identity = next;
			runner.drop();
			rerunOpen = false;
			onchanged?.();
		} catch (e) {
			if (job.id === jobId) runner.error = `Could not clear the episodes (${errorMessage(e, 'error')}).`;
		} finally {
			clearing = false;
		}
	}

	// The episode list behind the per-row picker: the active source's, else the
	// first source that ran and could answer (a nomatch disc still gets a list).
	const pickerSource = $derived(pickerSourceFor(identity, source));

	// The season list follows the re-run form's source while the form is open,
	// else the picker's source. Tracked on identity so a reload retries a list
	// that failed (a loaded one is skipped by its key).
	const seasonsSource = $derived<EpisodeSource | null>(rerunOpen ? rerun.source : pickerSource);
	$effect(() => {
		const src = seasonsSource;
		const jobId = job.id;
		void identity;
		if (!src || !canAct) return;
		untrack(() => seasonList.follow(jobId, src));
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
		untrack(() => episodeLists.want(jobId, src, needed));
	});

	// The by-hand choices of a shown row (its season already resolved). The
	// roles need no season; the episodes do.
	function optionsFor(row: EpisodeRow) {
		const season = row.season ?? discSeason;
		if (season == null) return ROLE_OPTIONS;
		return pickerOptions(
			episodeLists.get(season),
			season,
			row.seconds,
			usedEpisodeNumbers(placed.values(), season, row.trackId)
		);
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
			handError = errorMessage(e, 'Could not save');
			return false;
		}
		await reload();
		onchanged?.();
		return true;
	}

	async function setByHand(trackId: string, value: string) {
		const pick = parseHandPick(value);
		if (!pick) return;
		if ('role' in pick) return saveTrack(trackId, { role: pick.role });
		const row = rows.find((r) => r.trackId === trackId);
		const listSeason = row ? seasonOf(row) : null;
		const list = listSeason == null ? [] : episodeLists.get(listSeason);
		const name = pickedEpisodeName(list, listSeason, pick.season, pick.episode);
		const data = { role: 'episode' as const, season: pick.season, episode_number: pick.episode, episode_name: name };
		if (await saveTrack(trackId, data)) clearRowSeason(trackId);
	}

	// Fill the rest: preview the source over the tracks not set by hand (the
	// backend keeps each hand-set track and reserves its episode), shown in the
	// re-run form so its Apply is at hand. Offered once a track is set by hand
	// and another is not, however the others were placed.
	const canFill = $derived(!!pickerSource && rows.some((r) => r.handSet) && rows.some((r) => !r.handSet));
	function fillTheRest() {
		const src = pickerSource;
		if (!src) return;
		rerun = fillRestForm(src, job, rows);
		rerunOpen = true;
		runner.drop();
		return runner.run(rerunRequest(rerun, false));
	}

	async function revert(trackId: string) {
		if (await saveTrack(trackId, { revert_fields: [...REVERT] })) clearRowSeason(trackId);
	}
	// Include or leave a track out of the transcode output, from the same rows.
	function setExcluded(trackId: string, excluded: boolean) {
		return saveTrack(trackId, { excluded });
	}
</script>

{#snippet errorAlert()}
	{#if runner.error}
		<div class="alert alert-danger episode-panel-error" role="alert">
			<p class="alert-body">{runner.error}</p>
			<button
				type="button"
				class="btn btn-sm"
				disabled={runner.busy}
				onclick={() => runner.lastRequest && runner.run(runner.lastRequest)}>Try again</button
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
		<EpisodeStatusBar
			{view}
			{loading}
			{sourceLabel}
			showCount={showRows}
			placed={placedCount(rows)}
			total={rows.length}
		>
			{#snippet actions()}
				{#if canAct && canFill && !runner.preview}
					<button type="button" class="btn btn-sm" disabled={runner.busy} onclick={fillTheRest}>Fill the rest</button>
				{/if}
				{#if canAct}
					<button type="button" class="btn btn-sm" aria-expanded={rerunOpen} disabled={runner.busy} onclick={fixMatch}
						>Fix match</button
					>
				{/if}
				{#if canAct && rows.some((r) => r.code !== 'Not placed' && !r.handSet) && !runner.preview}
					<button type="button" class="btn btn-sm" disabled={runner.busy || clearing} onclick={clearEpisodes}
						>{clearing ? 'Clearing...' : 'Clear episodes'}</button
					>
				{/if}
				{#if others.length > 0 && view !== 'matching'}
					<button
						type="button"
						class="btn btn-ghost btn-sm"
						aria-expanded={othersOpen}
						onclick={() => (othersOpen = !othersOpen)}
					>
						View sources <Glyph name="chevron-down" />
					</button>
				{/if}
			{/snippet}
		</EpisodeStatusBar>

		{#if (ownSeason || altSeasons.length > 0) && !loading && !episodeIdentity.loadError}
			<div class="episode-panel-seasons" data-testid="season-fit">
				{#if ownSeason}
					<span class="episode-panel-fit"
						>{seasonName(ownSeason.season)}, {ownSeason.matches} of {ownSeason.total} titles</span
					>
				{/if}
				{#if alsoFits}<span class="episode-panel-text">Also fits {alsoFits}</span>{/if}
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

		<EpisodeStateAlert {loading} loadError={episodeIdentity.loadError} {view} {held} {failed} bind:whyOpen />

		{#if canAct && rerunOpen}
			<RerunPanel
				bind:form={rerun}
				sources={sourceOptions}
				seasons={seasonList.seasons}
				busy={runner.busy}
				preview={runner.preview && runner.previewSource
					? { changed: rows.filter((r) => r.changed).length, label: shortSourceLabel(runner.previewSource) }
					: null}
				onfieldchange={runner.drop}
				onpreview={() => runner.run(rerunRequest(rerun, false))}
				ondiscard={runner.drop}
				onapply={runner.applyPreview}
			>
				{@render errorAlert()}
			</RerunPanel>
		{:else}
			{@render errorAlert()}
		{/if}

		{#if showRows}
			<EpisodeRows
				rows={shownRows}
				fileNames={episodeIdentity.fileNames}
				matching={view === 'matching'}
				phone={phoneQuery.current}
				proposedLabel={runner.preview && runner.previewSource ? shortSourceLabel(runner.previewSource) : null}
				optionsFor={canAct && !runner.preview ? optionsFor : null}
				seasons={seasonList.seasons}
				panelSeason={discSeason}
				onseason={setRowSeason}
				onpick={setByHand}
				onrevert={revert}
				onexclude={canAct ? setExcluded : undefined}
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
	.episode-panel-seasons {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
	}
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
	.episode-panel-fit {
		font-size: 0.875rem;
		font-weight: 600;
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
