<script lang="ts">
	// Re-run the episode match with other settings (design spec 2026-10-02
	// section 4.3 #2): pick a source / season / disc / tolerance, preview the
	// outcome, then apply & pin it or discard it. Presentational - the panel
	// owns the requests.
	import type { Snippet } from 'svelte';
	import type { EpisodeSource } from '$lib/api/identity';
	import type { RerunForm } from './episodeModel';

	interface Props {
		form: RerunForm;
		sources: { id: EpisodeSource; label: string; disabled: boolean }[];
		/** The source's regular seasons; null when the list could not load (the
		 * season is then a number input). */
		seasons: number[] | null;
		busy: boolean;
		/** Changed-track count and source label of the preview on screen, if any. */
		preview: { changed: number; label: string } | null;
		onfieldchange: () => void;
		onpreview: () => void;
		ondiscard: () => void;
		onapply: () => void;
		children?: Snippet;
	}
	let {
		form = $bindable(),
		sources,
		seasons,
		busy,
		preview,
		onfieldchange,
		onpreview,
		ondiscard,
		onapply,
		children
	}: Props = $props();
	const uid = $props.id();

	// The job's season stays selectable while the list loads or lacks it.
	const listed = $derived(
		[...new Set([...(seasons ?? []), ...(typeof form.season === 'number' ? [form.season] : [])])]
			.filter((n) => n > 0)
			.sort((a, b) => a - b)
	);
	const seasonValue = $derived(form.season == null ? '' : String(form.season));

	function setSeason(value: string) {
		form.season = value === '' ? null : value === 'scan' ? 'scan' : Number(value);
		onfieldchange();
	}
</script>

<div class="panel panel-compact rerun-panel">
	<div class="rerun-panel-fields">
		<div class="field">
			<label class="field-label" for="{uid}-source">Source</label>
			<select id="{uid}-source" class="field-control" bind:value={form.source} onchange={onfieldchange}>
				{#each sources as s (s.id)}
					<option value={s.id} disabled={s.disabled}>{s.label}{s.disabled ? ' (not set up)' : ''}</option>
				{/each}
			</select>
		</div>
		<div class="field">
			<label class="field-label" for="{uid}-season">Season</label>
			{#if seasons}
				<select
					id="{uid}-season"
					class="field-control"
					value={seasonValue}
					onchange={(e) => setSeason(e.currentTarget.value)}
				>
					<option value="" disabled>-</option>
					<option value="scan">Scan all seasons</option>
					<option value="0">Specials</option>
					{#each listed as n (n)}
						<option value={String(n)}>Season {n}</option>
					{/each}
				</select>
			{:else}
				<input
					id="{uid}-season"
					class="field-control"
					type="number"
					min="0"
					placeholder="-"
					value={typeof form.season === 'number' ? form.season : ''}
					oninput={(e) => setSeason(e.currentTarget.value)}
				/>
			{/if}
		</div>
		<div class="field">
			<label class="field-label" for="{uid}-disc">Disc</label>
			<input
				id="{uid}-disc"
				class="field-control"
				type="number"
				min="1"
				placeholder="-"
				bind:value={form.disc}
				oninput={onfieldchange}
			/>
		</div>
		<div class="field">
			<label class="field-label" for="{uid}-tolerance">Tolerance (s)</label>
			<input
				id="{uid}-tolerance"
				class="field-control"
				type="number"
				min="1"
				max="1800"
				placeholder="Default"
				bind:value={form.tolerance}
				oninput={onfieldchange}
			/>
		</div>
		<button type="button" class="btn btn-primary rerun-panel-preview" disabled={busy} onclick={onpreview}>
			{busy && !preview ? 'Previewing...' : 'Preview'}
		</button>
	</div>

	{#if preview}
		<div class="rerun-panel-bar">
			<p class="rerun-panel-bar-text">
				{preview.changed}
				{preview.changed === 1 ? 'track changes' : 'tracks change'} if you apply {preview.label}. Nothing is saved yet.
			</p>
			<div class="rerun-panel-bar-actions">
				<button type="button" class="btn btn-ghost btn-sm" disabled={busy} onclick={ondiscard}>Discard</button>
				<button type="button" class="btn btn-primary btn-sm" disabled={busy} onclick={onapply}>
					Apply & pin {preview.label}
				</button>
			</div>
		</div>
	{/if}

	{@render children?.()}
</div>

<style>
	.rerun-panel {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}
	.rerun-panel-fields {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(7.5rem, 1fr));
		align-items: end;
		gap: 0.75rem;
	}
	.rerun-panel-preview {
		min-height: var(--control-h);
	}
	.rerun-panel-bar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 1rem;
		padding: 0.5rem 0.75rem;
		border-radius: var(--radius-md);
		background: var(--color-warning-soft);
		color: var(--color-on-warning-soft);
	}
	.rerun-panel-bar-text {
		font-size: 0.875rem;
	}
	.rerun-panel-bar-actions {
		display: flex;
		gap: 0.5rem;
		margin-left: auto;
	}
</style>
