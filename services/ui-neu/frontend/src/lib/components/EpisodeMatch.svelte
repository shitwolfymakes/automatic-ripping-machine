<script lang="ts">
	import type { JobDetailView, TrackView } from '$lib/types/api.gen';
	import { tvdbMatch, fetchTvdbEpisodes, updateTrack, fetchNamingPreview } from '$lib/api/jobs';
	import { reveal } from '$lib/transitions';
	import { isAdmin } from '$lib/stores/auth';

	// ---------------------------------------------------------------------------
	// MISSING in v3 — TVDB episode matching / listing have no v3 endpoint
	// (tvdbMatch / fetchTvdbEpisodes REJECT at runtime). This screen is
	// feature-gated OFF; kept type-clean only. The BFF response shapes
	// (TvdbEpisode / TvdbMatch / NamingPreviewTrack) were removed from jobs.ts,
	// so they are declared LOCALLY here purely to type the now-dead state. No v3
	// type fits — the feature is dead. (updateTrack EXISTS — bulk-PATCH wrap.)
	// ---------------------------------------------------------------------------
	interface TvdbEpisode {
		number: number;
		name: string;
		runtime: number;
		aired: string;
	}
	interface TvdbMatchEntry {
		track_number: string;
		episode_number: number;
		episode_name: string;
		episode_runtime: number;
	}
	interface NamingPreviewTrack {
		rendered_title?: string;
	}

	interface Props {
		job: JobDetailView;
		// season / season_auto / disc_number / disc_total / tvdb_id / imdb_id have
		// no JobView equivalent (BFF-only); accept as optional props so the (dead)
		// screen still type-checks.
		season?: string | null;
		seasonAuto?: string | null;
		discNumber?: number | null;
		discTotal?: number | null;
		tvdbId?: number | null;
		imdbId?: string | null;
		onapply?: () => void;
	}

	let {
		job,
		season = null,
		seasonAuto = null,
		discNumber = null,
		discTotal = null,
		tvdbId = null,
		imdbId = null,
		onapply
	}: Props = $props();

	// v3 JobDetailView nests tracks under `job.tracks`.
	let tracks = $derived<TrackView[]>(job.tracks || []);

	// Controls - initialized empty, synced from job props via $effect
	let seasonInput = $state('');
	let discInput = $state('');
	let discTotalInput = $state('');
	let toleranceInput = $state('600');
	let controlsSynced = $state(false);

	// Sync controls from props when they become available
	$effect(() => {
		if (!controlsSynced) {
			const s = season || seasonAuto || '';
			const d = discNumber?.toString() || '';
			const dt = discTotal?.toString() || '';
			if (s || d || dt) {
				seasonInput = s;
				discInput = d;
				discTotalInput = dt;
				controlsSynced = true;
			}
		}
	});

	// State
	let loading = $state(false);
	let error = $state<string | null>(null);
	let matches = $state<TvdbMatchEntry[]>([]);
	let episodes = $state<TvdbEpisode[]>([]);
	let namingPreviews = $state<Record<string, NamingPreviewTrack>>({});
	let applying = $state(false);

	// Editable assignments: track index (string) -> episode_number (null = unassigned)
	let assignments = $state<Record<string, number | null>>({});

	// Derived — v3 tracks carry `index` / `duration_seconds`.
	let mainTracks = $derived(
		tracks
			.filter((t) => (t.duration_seconds ?? 0) >= 120)
			.sort((a, b) => a.index - b.index)
	);
	let shortTracks = $derived(tracks.filter((t) => (t.duration_seconds ?? 0) < 120));
	let matchCount = $derived(
		Object.values(assignments).filter((v) => v !== null && v !== undefined).length
	);
	let unmatched = $derived(mainTracks.length - matchCount);

	function formatDuration(seconds: number | null | undefined): string {
		if (!seconds) return '-';
		const m = Math.floor(seconds / 60);
		const s = seconds % 60;
		return `${m}:${s.toString().padStart(2, '0')}`;
	}

	function deltaTone(trackLen: number | null | undefined, epRuntime: number | null): string | undefined {
		if (!trackLen || !epRuntime) return undefined;
		const delta = Math.abs(trackLen - epRuntime * 60);
		if (delta < 60) return 'success';
		if (delta < 180) return 'warning';
		return 'danger';
	}

	function deltaText(trackLen: number | null | undefined, epRuntime: number | null): string {
		if (!trackLen || !epRuntime) return '-';
		const delta = trackLen - epRuntime * 60;
		const abs = Math.abs(delta);
		const sign = delta >= 0 ? '+' : '-';
		if (abs < 60) return `${sign}${abs}s`;
		return `${sign}${Math.floor(abs / 60)}m${(abs % 60).toString().padStart(2, '0')}s`;
	}

	async function loadEpisodeList(s: number, fallbackMatches?: TvdbMatchEntry[]) {
		try {
			const epResult = (await fetchTvdbEpisodes(job.job.id, s)) as { episodes: TvdbEpisode[] };
			// API returns runtime in seconds - always convert to minutes
			episodes = epResult.episodes.map((ep) => ({
				...ep,
				runtime: Math.round(ep.runtime / 60)
			}));
		} catch {
			if (fallbackMatches?.length) {
				const seen = new Set<number>();
				const fallback: TvdbEpisode[] = [];
				for (const m of fallbackMatches) {
					if (!seen.has(m.episode_number)) {
						seen.add(m.episode_number);
						fallback.push({
							number: m.episode_number,
							name: m.episode_name,
							runtime: m.episode_runtime ? Math.round(m.episode_runtime / 60) : 0,
							aired: ''
						});
					}
				}
				episodes = fallback;
			}
		}
	}

	async function runMatch() {
		loading = true;
		error = null;
		try {
			const s = seasonInput ? Number(seasonInput) : null;
			const result = (await tvdbMatch(job.job.id, {
				season: s,
				tolerance: Number(toleranceInput) || 300,
				apply: false,
				disc_number: discInput ? Number(discInput) : null,
				disc_total: discTotalInput ? Number(discTotalInput) : null
			})) as { success?: boolean; error?: string; matches: TvdbMatchEntry[]; season: number };

			if (!result.success) {
				error = result.error || 'Match failed';
				return;
			}

			matches = result.matches;

			// Update season input if auto-detected
			if (!seasonInput && result.season) {
				seasonInput = result.season.toString();
			}

			// Populate assignments from matches
			assignments = {};
			for (const m of result.matches) {
				assignments[m.track_number] = m.episode_number;
			}

			// Fetch ALL season episodes for dropdowns
			if (result.season) {
				await loadEpisodeList(result.season, result.matches);
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Match failed';
		} finally {
			loading = false;
		}
	}

	async function applyMatches() {
		applying = true;
		error = null;
		try {
			// Apply via tvdb-match with apply=true for auto-matched tracks
			const s = seasonInput ? Number(seasonInput) : null;
			await tvdbMatch(job.job.id, {
				season: s,
				tolerance: Number(toleranceInput) || 300,
				apply: true,
				disc_number: discInput ? Number(discInput) : null,
				disc_total: discTotalInput ? Number(discTotalInput) : null
			});

			// Apply manual overrides for tracks that differ from auto-match.
			// updateTrack EXISTS (bulk-PATCH wrap) and selects rows by track id.
			for (const track of mainTracks) {
				const tn = String(track.index);
				const assigned = assignments[tn];
				const autoMatch = matches.find((m) => m.track_number === tn);

				if (assigned !== undefined && assigned !== (autoMatch?.episode_number ?? null)) {
					const ep = episodes.find((e) => e.number === assigned);
					await updateTrack(job.job.id, track.id, {
						episode_number: assigned ?? null,
						episode_name: ep?.name ?? ''
					});
				}
			}

			// Fetch rendered filenames after apply
			await loadNamingPreviews();
			onapply?.();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Apply failed';
		} finally {
			applying = false;
		}
	}

	async function loadNamingPreviews() {
		try {
			const result = await fetchNamingPreview(job.job.id);
			const map: Record<string, NamingPreviewTrack> = {};
			for (const t of result.items) {
				if (t.track_number != null) {
					map[String(t.track_number)] = { rendered_title: t.output_name };
				}
			}
			namingPreviews = map;
		} catch {
			// Non-critical - silently skip
		}
	}

	function clearAll() {
		assignments = {};
		matches = [];
		episodes = [];
	}

	function getEpisodeForTrack(trackKey: string): TvdbEpisode | undefined {
		const epNum = assignments[trackKey];
		if (epNum == null) return undefined;
		return episodes.find((e) => e.number === epNum);
	}

	// Tracks with existing episode assignments (from previous Apply)
	let existingMatches = $derived(mainTracks.filter((t) => t.episode_number));

	// On mount: if tracks have existing episodes, restore into assignments
	// and load full episode list for dropdowns. Otherwise auto-run match.
	$effect(() => {
		if (mainTracks.length > 0 && matches.length === 0) {
			if (existingMatches.length > 0) {
				// Populate assignments from DB track data
				for (const t of existingMatches) {
					assignments[String(t.index)] = Number(t.episode_number);
				}
				// Set matches so the interactive table renders
				matches = existingMatches.map((t) => ({
					track_number: String(t.index),
					episode_number: Number(t.episode_number),
					episode_name: t.episode_name || '',
					episode_runtime: 0
				}));
				// Load full episode list for dropdowns
				if (tvdbId) {
					const s = Number(seasonInput || season || seasonAuto || 1);
					loadEpisodeList(s);
				}
			} else if (tvdbId || imdbId) {
				runMatch();
			}
		}
	});
</script>

<div class="stack">
	<!-- Controls bar (always visible) -->
	<div class="flex flex-wrap items-center gap-3 panel-section episode-match-controls">
		<div class="flex items-center gap-1.5">
			<span class="eyebrow episode-match-label">Season</span>
			<input
				type="number"
				bind:value={seasonInput}
				min="1"
				class="w-12 episode-match-mini-input"
			/>
		</div>
		<div class="flex items-center gap-1.5">
			<span class="eyebrow episode-match-label">Disc</span>
			<input
				type="number"
				bind:value={discInput}
				min="1"
				class="w-12 episode-match-mini-input"
			/>
			<span class="episode-match-of">of</span>
			<input
				type="number"
				bind:value={discTotalInput}
				min="1"
				class="w-12 episode-match-mini-input"
			/>
		</div>
		<div class="flex items-center gap-1.5">
			<span class="eyebrow episode-match-label">Tolerance</span>
			<input
				type="number"
				bind:value={toleranceInput}
				min="60"
				step="60"
				class="w-16 episode-match-mini-input"
			/>
			<span class="episode-match-sec">sec</span>
		</div>
		<button
			onclick={runMatch}
			disabled={loading}
			class="btn btn-primary episode-match-run-btn"
		>
			{loading ? 'Matching...' : 'Match'}
		</button>
		{#if matches.length > 0}
			<div class="ml-auto flex items-center gap-2 episode-match-summary">
				<span class="episode-match-summary-tone" data-tone="success">{matchCount} matched</span>
				<span class="episode-match-dot">&middot;</span>
				{#if unmatched > 0}
					<span class="episode-match-summary-tone" data-tone="warning">{unmatched} unmatched</span>
				{:else}
					<span class="episode-match-dot">0 unmatched</span>
				{/if}
				<span class="episode-match-dot">&middot;</span>
				<span class="episode-match-dot">{shortTracks.length} skipped</span>
			</div>
		{/if}
	</div>

	<!-- Error -->
	{#if error}
		<div class="alert alert-danger">
			{error}
		</div>
	{/if}

	<!-- Match table -->
	{#if matches.length > 0 || Object.keys(assignments).length > 0}
		<div class="overflow-x-auto">
			<table class="table episode-match-table">
				<colgroup>
					<col />
					<col />
					<col />
					<col />
					<col />
					<col />
				</colgroup>
				<thead>
					<tr>
						<th class="table-header">Track</th>
						<th class="table-header">Duration</th>
						<th class="table-header">Episode</th>
						<th class="table-header">Title</th>
						<th class="table-header episode-match-right">TVDB</th>
						<th class="table-header episode-match-right">Delta</th>
					</tr>
				</thead>
				<tbody>
					{#each mainTracks as track}
						{@const tn = String(track.index)}
						{@const ep = getEpisodeForTrack(tn)}
						<tr class="table-row">
							<td class="table-cell">
								<span class="episode-match-track-num">T{tn}</span>
								<span class="ml-1 episode-match-source-ref">{(track.source_ref ?? '').slice(0, 30)}</span>
							</td>
							<td class="table-cell episode-match-duration">{formatDuration(track.duration_seconds)}</td>
							<td class="table-cell">
								<select
									class="w-full truncate episode-match-select"
									data-assigned={assignments[tn] != null}
									value={assignments[tn] ?? ''}
									onchange={(e) => {
										const val = (e.target as HTMLSelectElement).value;
										assignments[tn] = val ? Number(val) : null;
									}}
								>
									<option value="">- None -</option>
									{#each [...episodes].sort((a, b) => a.number - b.number) as episode}
										<option value={episode.number}>
											E{episode.number} - {episode.name} ({episode.runtime}m)
										</option>
									{/each}
								</select>
							</td>
							<td class="table-cell episode-match-title">
								{namingPreviews[tn]?.rendered_title || ep?.name || '-'}
							</td>
							<td class="table-cell episode-match-right episode-match-runtime">{ep ? `${ep.runtime}m` : '-'}</td>
							<td class="table-cell episode-match-right episode-match-delta" data-tone={deltaTone(track.duration_seconds, ep?.runtime ?? null)}>
								{deltaText(track.duration_seconds, ep?.runtime ?? null)}
							</td>
						</tr>
					{/each}
					{#if shortTracks.length > 0}
						<tr class="table-row" data-disabled="true">
							<td class="table-cell episode-match-skip-note" colspan="6">
								{shortTracks.length} short track{shortTracks.length > 1 ? 's' : ''} skipped (menus, intros)
							</td>
						</tr>
					{/if}
				</tbody>
			</table>
		</div>

		<!-- Actions -->
		<div class="flex items-center gap-2">
			{#if $isAdmin}
				<button
					in:reveal
					onclick={applyMatches}
					disabled={applying || matchCount === 0}
					class="btn episode-match-success-btn episode-match-wide-btn"
				>
					{applying ? 'Applying...' : 'Apply Matches'}
				</button>
				<button
					in:reveal
					onclick={clearAll}
					class="btn episode-match-clear-btn episode-match-wide-btn"
				>
					Clear All
				</button>
			{/if}
			<span class="ml-auto episode-match-hint">
				Change season/disc and re-match to try different assignments.
			</span>
		</div>
	{:else if loading}
		<div class="flex items-center justify-center py-8">
			<div class="flex items-center gap-2 episode-match-loading">
				<svg class="h-5 w-5 episode-match-spinner" fill="none" viewBox="0 0 24 24">
					<circle class="episode-match-spinner-track" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
					<path class="episode-match-spinner-arc" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
				</svg>
				Matching episodes...
			</div>
		</div>
	{:else if !error && !applying}
		<div class="py-6 episode-match-empty episode-match-center">
			{#if !tvdbId && !imdbId}
				No IMDB or TVDB ID set. Use <strong>Search</strong> to identify the show first.
			{:else if mainTracks.length === 0}
				No tracks found. The prescan may still be running.
			{:else}
				Click <strong>Match</strong> to auto-assign episodes to tracks.
			{/if}
		</div>
	{/if}
</div>

<style>
	.episode-match-controls { background: var(--color-primary-tint-1); }
	.episode-match-label { color: var(--color-text-muted); }
	.episode-match-mini-input { border-radius: var(--radius-sm); border: 1px solid var(--color-border); background: var(--color-surface); padding: 0.125rem 0.375rem; text-align: center; font-size: 0.75rem; line-height: 1rem; color: var(--color-text); }
	.episode-match-of { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-faint); }
	.episode-match-sec { font-size: 10px; color: var(--color-text-faint); }
	.episode-match-summary { font-size: 0.75rem; line-height: 1rem; }
	.episode-match-summary-tone[data-tone="success"] { color: var(--color-success); }
	.episode-match-summary-tone[data-tone="warning"] { color: var(--color-on-warning-soft); }
	.episode-match-dot { color: var(--color-text-muted); }
	.episode-match-table { table-layout: fixed; }
	.episode-match-table col:nth-child(1) { width: 25%; }
	.episode-match-table col:nth-child(2) { width: 8%; }
	.episode-match-table col:nth-child(3) { width: 28%; }
	.episode-match-table col:nth-child(4) { width: 23%; }
	.episode-match-table col:nth-child(5) { width: 8%; }
	.episode-match-table col:nth-child(6) { width: 8%; }
	.episode-match-right { text-align: right; }
	.episode-match-center { text-align: center; }
	.episode-match-track-num { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
	.episode-match-source-ref { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-faint); }
	.episode-match-duration { color: var(--color-text-secondary); }
	.episode-match-select { border-radius: var(--radius-sm); border: 1px solid var(--color-border); background: var(--color-surface); padding: 0.125rem 0.375rem; font-size: 0.75rem; line-height: 1rem; color: var(--color-text-faint); }
	.episode-match-select[data-assigned="true"] { color: var(--color-success); }
	.episode-match-title { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-secondary); }
	.episode-match-runtime { color: var(--color-text-faint); }
	.episode-match-delta { font-size: inherit; }
	.episode-match-delta[data-tone="success"] { color: var(--color-success); }
	.episode-match-delta[data-tone="warning"] { color: var(--color-on-warning-soft); }
	.episode-match-delta[data-tone="danger"] { color: var(--color-danger); }
	.episode-match-skip-note { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
	.episode-match-success-btn { border: 0; background: var(--color-success); color: var(--color-on-primary); }
	.episode-match-clear-btn { box-shadow: 0 0 0 1px var(--color-border-strong); color: var(--color-text-muted); }
	/* the original Match button was px-3 py-1 (0.75rem/0.25rem); Apply
	   Matches / Clear All were px-4 py-1.5 (1rem/0.375rem) */
	.episode-match-run-btn { padding: 0.25rem 0.75rem; }
	.episode-match-wide-btn { padding: 0.375rem 1rem; }
	.episode-match-success-btn:hover { filter: brightness(0.9); }
	.episode-match-hint { font-size: 11px; color: var(--color-text-faint); }
	.episode-match-loading { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-faint); }
	.episode-match-spinner { animation: episode-match-spin 1s linear infinite; }
	.episode-match-spinner-track { opacity: 0.25; }
	.episode-match-spinner-arc { opacity: 0.75; }
	@keyframes episode-match-spin { to { transform: rotate(360deg); } }
	.episode-match-empty { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-faint); }
</style>
