<script lang="ts">
	import type { JobDetailView, TrackView } from '$lib/types/api.gen';
	import { tvdbMatch, fetchTvdbEpisodes } from '$lib/api/jobs';

	// ---------------------------------------------------------------------------
	// MISSING in v3 — TVDB episode matching / listing have no v3 endpoint
	// (tvdbMatch / fetchTvdbEpisodes REJECT at runtime). This screen is
	// feature-gated OFF; kept type-clean only. The BFF response shapes were
	// removed from jobs.ts, so they are declared LOCALLY here purely to type the
	// now-dead state. No v3 type fits — the feature is dead.
	// ---------------------------------------------------------------------------
	interface TvdbMatch {
		track_number: string;
		episode_number: number;
		episode_name: string;
		episode_runtime: number;
	}
	interface TvdbAlternative {
		season: number;
		match_count: number;
	}
	interface TvdbMatchResponse {
		success?: boolean;
		matcher?: string;
		season: number;
		matches: TvdbMatch[];
		match_count: number;
		score: number;
		alternatives: TvdbAlternative[];
		error?: string;
	}
	interface TvdbEpisode {
		number: number;
		name: string;
		runtime: number;
		aired: string;
	}
	interface TvdbEpisodesResponse {
		episodes: TvdbEpisode[];
		tvdb_id?: number | null;
		season: number;
	}

	interface Props {
		job: JobDetailView;
		// season / season_auto / tvdb_id have no JobView equivalent (BFF-only);
		// accept them as optional props so the (dead) screen still type-checks.
		season?: string | null;
		seasonAuto?: string | null;
		tvdbId?: number | null;
		onapply?: () => void;
	}

	let { job, season = null, seasonAuto = null, tvdbId = null, onapply }: Props = $props();

	// v3 JobDetailView nests tracks under `job.tracks`.
	let tracks = $derived<TrackView[]>(job.tracks || []);

	// --- Tabs ---
	let activeTab = $state<'match' | 'browse'>('match');

	// --- Match state ---
	let seasonInput = $state(season || seasonAuto || '');
	let toleranceInput = $state('300');
	let autoDetect = $state(!(season || seasonAuto));
	let loading = $state(false);
	let error = $state<string | null>(null);
	let result = $state<TvdbMatchResponse | null>(null);
	let applying = $state(false);
	let applyFeedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	// Per-match selection (checked = will be applied)
	let selectedMatches = $state<Set<string>>(new Set());

	let selectedCount = $derived(selectedMatches.size);

	// --- Browse state ---
	let browseSeason = $state(Number(season || seasonAuto) || 1);
	let browseLoading = $state(false);
	let browseError = $state<string | null>(null);
	let browseResult = $state<TvdbEpisodesResponse | null>(null);

	// Build a map of track durations for display (track index → seconds).
	let trackLengthMap = $derived(
		Object.fromEntries(tracks.map((t) => [String(t.index), t.duration_seconds]))
	);

	// Build a map of track episode assignments for browse view.
	let trackEpisodeMap = $derived(
		Object.fromEntries(
			tracks
				.filter((t) => t.episode_number)
				.map((t) => [String(t.episode_number), String(t.index)])
		)
	);

	async function handlePreview() {
		loading = true;
		error = null;
		result = null;
		applyFeedback = null;
		try {
			result = (await tvdbMatch(job.job.id, {
				season: autoDetect ? null : Number(seasonInput) || null,
				tolerance: Number(toleranceInput) || 300,
				apply: false
			})) as TvdbMatchResponse;
			// Select all matches by default
			selectedMatches = new Set(result.matches.map((m) => m.track_number));
		} catch (e) {
			error = e instanceof Error ? e.message : 'TVDB match failed';
		} finally {
			loading = false;
		}
	}

	async function handleApply() {
		if (!result || selectedCount === 0) return;
		applying = true;
		applyFeedback = null;
		try {
			await tvdbMatch(job.job.id, {
				season: result.season ?? null,
				tolerance: Number(toleranceInput) || 300,
				apply: true
			});
			applyFeedback = {
				type: 'success',
				message: `Applied ${result.matches.length} episode matches (S${String(result.season).padStart(2, '0')})`
			};
			onapply?.();
		} catch (e) {
			applyFeedback = {
				type: 'error',
				message: e instanceof Error ? e.message : 'Apply failed'
			};
		} finally {
			applying = false;
		}
	}

	function toggleMatch(trackNumber: string) {
		const next = new Set(selectedMatches);
		if (next.has(trackNumber)) {
			next.delete(trackNumber);
		} else {
			next.add(trackNumber);
		}
		selectedMatches = next;
	}

	function toggleAllMatches() {
		if (!result) return;
		if (selectedCount === result.matches.length) {
			selectedMatches = new Set();
		} else {
			selectedMatches = new Set(result.matches.map((m) => m.track_number));
		}
	}

	function switchToSeason(s: number) {
		autoDetect = false;
		seasonInput = String(s);
		handlePreview();
	}

	async function handleBrowse() {
		browseLoading = true;
		browseError = null;
		browseResult = null;
		try {
			browseResult = (await fetchTvdbEpisodes(job.job.id, browseSeason)) as TvdbEpisodesResponse;
		} catch (e) {
			browseError = e instanceof Error ? e.message : 'Failed to fetch episodes';
		} finally {
			browseLoading = false;
		}
	}

	function formatRuntime(seconds: number | null | undefined): string {
		if (!seconds) return '--';
		const m = Math.floor(seconds / 60);
		const s = seconds % 60;
		return `${m}:${String(s).padStart(2, '0')}`;
	}

	function formatDelta(trackLen: number | null, epRuntime: number): string {
		if (!trackLen) return '--';
		const delta = trackLen - epRuntime;
		const sign = delta >= 0 ? '+' : '';
		return `${sign}${delta}s`;
	}


</script>

<div class="stack">
	<!-- TVDB ID status -->
	<div class="flex items-center gap-2">
		{#if tvdbId}
			<span class="mono tvdb-match-id">TVDB {tvdbId}</span>
		{:else}
			<span class="tvdb-match-id-empty">TVDB ID resolves on first match</span>
		{/if}
		{#if seasonAuto}
			<span class="badge badge-sm">
				Season {seasonAuto}
			</span>
		{/if}
	</div>

	<!-- Tab bar -->
	<div class="tabs">
		<button
			data-selected={activeTab === 'match'}
			onclick={() => (activeTab = 'match')}
			class="tabs-tab"
		>
			Match Tracks
		</button>
		<button
			data-selected={activeTab === 'browse'}
			onclick={() => (activeTab = 'browse')}
			class="tabs-tab"
		>
			Browse Episodes
		</button>
	</div>

	<!-- ===== MATCH TAB ===== -->
	{#if activeTab === 'match'}
		<!-- Controls -->
		<div class="flex flex-wrap items-end gap-3">
			<label class="flex items-center gap-2">
				<input
					type="checkbox"
					bind:checked={autoDetect}
					class="tvdb-match-checkbox"
				/>
				<span class="tvdb-match-checkbox-label">Auto-detect season</span>
			</label>
			{#if !autoDetect}
				<label class="field">
					<span class="field-label tvdb-match-field-label">Season</span>
					<input
						type="number"
						bind:value={seasonInput}
						min="1"
						class="w-20"
					/>
				</label>
			{/if}
			<label class="field">
				<span class="field-label tvdb-match-field-label">Tolerance (sec)</span>
				<input
					type="number"
					bind:value={toleranceInput}
					min="60"
					step="30"
					class="w-24"
				/>
			</label>
			<button
				onclick={handlePreview}
				disabled={loading}
				class="btn btn-primary tvdb-match-action-btn"
			>
				{loading ? 'Matching...' : 'Preview Match'}
			</button>
		</div>

		{#if error}
			<p class="field-error">{error}</p>
		{/if}

		<!-- Results -->
		{#if result}
			<div class="stack">
				<!-- Summary -->
				<div class="flex flex-wrap items-center gap-3">
					<span class="tvdb-match-summary">
						Season {result.season}: {result.match_count} match{result.match_count !== 1
							? 'es'
							: ''}
					</span>
					{#if result.score > 0}
						<span class="tvdb-match-summary-note">avg delta {result.score}s</span>
					{/if}
				</div>

				<!-- Alternative seasons (clickable to re-match) -->
				{#if result.alternatives.length > 0}
					<div class="flex flex-wrap items-center gap-1.5">
						<span class="tvdb-match-also-try">Also try:</span>
						{#each result.alternatives as alt}
							{#if alt.match_count > 0}
								<button
									onclick={() => switchToSeason(alt.season)}
									class="chip chip-info chip-sm"
								>
									S{String(alt.season).padStart(2, '0')} ({alt.match_count} match{alt.match_count !== 1 ? 'es' : ''})
								</button>
							{/if}
						{/each}
					</div>
				{/if}

				<!-- Match table -->
				{#if result.matches.length > 0}
					<div class="overflow-x-auto tvdb-match-table-scroll">
						<table class="table">
							<thead>
								<tr>
									<th class="table-header w-8">
										<input
											type="checkbox"
											checked={selectedCount === result.matches.length}
											onchange={toggleAllMatches}
											class="tvdb-match-checkbox"
										/>
									</th>
									<th class="table-header">Track</th>
									<th class="table-header">Track Length</th>
									<th class="table-header">Episode</th>
									<th class="table-header">Name</th>
									<th class="table-header">TVDB Runtime</th>
									<th class="table-header">Delta</th>
								</tr>
							</thead>
							<tbody>
								{#each result.matches as match}
									{@const trackLen =
										trackLengthMap[match.track_number] ?? null}
									{@const delta =
										trackLen != null
											? Math.abs(trackLen - match.episode_runtime)
											: null}
									{@const selected = selectedMatches.has(
										match.track_number
									)}
									<tr
										class="table-row"
										data-disabled={!selected}
									>
										<td class="table-cell">
											<input
												type="checkbox"
												checked={selected}
												onchange={() =>
													toggleMatch(match.track_number)}
												class="tvdb-match-checkbox"
											/>
										</td>
										<td class="table-cell mono"
											>{match.track_number}</td
										>
										<td class="table-cell"
											>{formatRuntime(trackLen)}</td
										>
										<td class="table-cell tvdb-match-episode-cell"
											>S{String(result.season).padStart(
												2,
												'0'
											)}E{String(
												match.episode_number
											).padStart(2, '0')}</td
										>
										<td class="table-cell"
											>{match.episode_name}</td
										>
										<td class="table-cell"
											>{formatRuntime(
												match.episode_runtime
											)}</td
										>
										<td
											class="table-cell mono tvdb-match-delta"
											data-tone={delta != null && delta < 60
												? 'success'
												: delta != null && delta < 120
													? 'warning'
													: 'muted'}
										>
											{formatDelta(trackLen, match.episode_runtime)}
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>

					<!-- Unmatched tracks -->
					{@const matchedTracks = new Set(
						result.matches.map((m) => m.track_number)
					)}
					{@const unmatchedTracks = tracks.filter(
						(t) =>
							!matchedTracks.has(String(t.index)) &&
							(t.duration_seconds ?? 0) >= 120
					)}
					{#if unmatchedTracks.length > 0}
						<p class="tvdb-match-unmatched">
							Unmatched tracks: {unmatchedTracks
								.map(
									(t) =>
										`#${t.index} (${formatRuntime(t.duration_seconds)})`
								)
								.join(', ')}
						</p>
					{/if}

					<!-- Apply button -->
					<div class="flex items-center gap-3">
						<button
							onclick={handleApply}
							disabled={applying || selectedCount === 0}
							class="btn tvdb-match-success-btn tvdb-match-action-btn"
						>
							{applying
								? 'Applying...'
								: `Apply ${selectedCount} Match${selectedCount !== 1 ? 'es' : ''}`}
						</button>
						{#if applyFeedback}
							<span
								class="tvdb-match-feedback"
								data-tone={applyFeedback.type}
							>
								{applyFeedback.message}
							</span>
						{/if}
					</div>
				{:else}
					<p class="tvdb-match-empty">
						No matches found. Try adjusting the tolerance or season.
					</p>
				{/if}
			</div>
		{/if}

	<!-- ===== BROWSE TAB ===== -->
	{:else if activeTab === 'browse'}
		<div class="flex flex-wrap items-end gap-3">
			<label class="field">
				<span class="field-label tvdb-match-field-label">Season</span>
				<input
					type="number"
					bind:value={browseSeason}
					min="1"
					class="w-20"
				/>
			</label>
			<button
				onclick={handleBrowse}
				disabled={browseLoading}
				class="btn btn-primary tvdb-match-action-btn"
			>
				{browseLoading ? 'Loading...' : 'Load Episodes'}
			</button>
		</div>

		{#if browseError}
			<p class="field-error">{browseError}</p>
		{/if}

		{#if browseResult}
			<div class="stack-sm stack">
				<p class="tvdb-match-summary-note">
					{browseResult.episodes.length} episode{browseResult.episodes.length !== 1 ? 's' : ''} in Season {browseResult.season}
					{#if browseResult.tvdb_id}
						<span class="mono">(TVDB {browseResult.tvdb_id})</span>
					{/if}
				</p>

				{#if browseResult.episodes.length > 0}
					<div class="overflow-x-auto tvdb-match-table-scroll">
						<table class="table">
							<thead>
								<tr>
									<th class="table-header w-16">#</th>
									<th class="table-header">Episode Name</th>
									<th class="table-header w-24">Runtime</th>
									<th class="table-header w-24">Aired</th>
									<th class="table-header w-24">Matched</th>
								</tr>
							</thead>
							<tbody>
								{#each browseResult.episodes as ep}
									{@const matchedTrack = trackEpisodeMap[String(ep.number)]}
									<tr class="table-row">
										<td class="table-cell mono tvdb-match-muted"
											>E{String(ep.number).padStart(2, '0')}</td
										>
										<td class="table-cell"
											>{ep.name}</td
										>
										<td class="table-cell"
											>{formatRuntime(ep.runtime)}</td
										>
										<td class="table-cell tvdb-match-summary-note"
											>{ep.aired || '--'}</td
										>
										<td class="table-cell">
											{#if matchedTrack}
												<span class="badge badge-sm badge-success">
													Track {matchedTrack}
												</span>
											{:else}
												<span class="tvdb-match-empty-sm">--</span>
											{/if}
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{:else}
					<p class="tvdb-match-empty">
						No episodes found for this season.
					</p>
				{/if}
			</div>
		{/if}
	{/if}
</div>

<style>
	.tvdb-match-id { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
	.tvdb-match-episode-cell { font-weight: 500; }
	.tvdb-match-id-empty { font-style: italic; color: var(--color-text-faint); }
	.tvdb-match-checkbox { width: 1rem; height: 1rem; border-radius: var(--radius-sm); accent-color: var(--color-primary); }
	.tvdb-match-checkbox-label { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-secondary); }
	.tvdb-match-field-label { font-size: 0.75rem; line-height: 1rem; }
	.tvdb-match-summary { font-weight: 500; color: var(--color-text); }
	.tvdb-match-summary-note { color: var(--color-text-muted); }
	.tvdb-match-also-try { font-size: 0.75rem; line-height: 1rem; font-weight: 500; color: var(--color-text-faint); }
	.tvdb-match-table-scroll { border: 1px solid var(--color-border); border-radius: var(--radius-lg); }
	.tvdb-match-delta { font-size: 0.75rem; line-height: 1rem; }
	.tvdb-match-delta[data-tone="success"] { color: var(--color-success); }
	.tvdb-match-delta[data-tone="warning"] { color: var(--color-on-warning-soft); }
	.tvdb-match-delta[data-tone="muted"] { color: var(--color-text-muted); }
	.tvdb-match-unmatched { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-faint); }
	.tvdb-match-success-btn { border: 0; background: var(--color-success); color: var(--color-on-primary); }
	/* the original action buttons were px-3 py-1.5 (0.75rem/0.375rem) */
	.tvdb-match-action-btn { padding: 0.375rem 0.75rem; }
	.tvdb-match-success-btn:hover { filter: brightness(0.9); }
	.tvdb-match-feedback { font-size: 0.75rem; line-height: 1rem; }
	.tvdb-match-feedback[data-tone="success"] { color: var(--color-success); }
	.tvdb-match-feedback[data-tone="error"] { color: var(--color-danger); }
	.tvdb-match-empty { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-faint); }
	.tvdb-match-empty-sm { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-faint); }
	.tvdb-match-muted { color: var(--color-text-muted); }
</style>
