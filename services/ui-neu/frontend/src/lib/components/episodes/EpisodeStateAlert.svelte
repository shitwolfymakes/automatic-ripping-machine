<script lang="ts">
	// The Match episodes tab's one alert for its state: the identity
	// could not load, no episode source is set up, the match is a guess
	// (with why, on request), or no source could place the tracks.
	import type { PanelState } from '../../episodes/episode-model';
	import Glyph from '../Glyph.svelte';

	interface Props {
		/** The first load is still running: no alert yet. */
		loading: boolean;
		loadError: string | null;
		view: PanelState;
		/** A held result's one-line reading and its other reasons. */
		held: { line: string; more: string[] } | null;
		failed: { id: string; label: string; detail: string | null }[];
		/** The why disclosure is open. The panel owns it, so a new job closes it. */
		whyOpen: boolean;
	}
	let { loading, loadError, view, held, failed, whyOpen = $bindable() }: Props = $props();
</script>

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
{:else if view === 'unsure' && held}
	<div class="alert alert-warning">
		<p class="alert-title episode-panel-hold-line">
			<span>{held.line}</span>
			{#if held.more.length > 0}
				<button
					type="button"
					class="btn btn-ghost btn-sm episode-panel-why"
					aria-label="Why this is a guess"
					aria-expanded={whyOpen}
					onclick={() => (whyOpen = !whyOpen)}><Glyph name="info" /></button
				>
			{/if}
		</p>
		{#if whyOpen}
			<ul class="episode-panel-why-list">
				{#each held.more as reason (reason)}
					<li>{reason}</li>
				{/each}
			</ul>
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

<style>
	.episode-panel-hold-line {
		display: flex;
		align-items: center;
		gap: 0.25rem;
	}
	.episode-panel-why {
		min-height: 1.5rem;
		padding: 0 0.25rem;
		color: inherit;
	}
	.episode-panel-why-list {
		margin: 0.25rem 0 0;
		padding-left: 1.25rem;
	}
</style>
