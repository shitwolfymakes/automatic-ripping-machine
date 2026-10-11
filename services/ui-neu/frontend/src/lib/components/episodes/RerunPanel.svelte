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
		busy,
		preview,
		onfieldchange,
		onpreview,
		ondiscard,
		onapply,
		children
	}: Props = $props();
	const uid = $props.id();
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
			<input
				id="{uid}-season"
				class="field-control"
				type="number"
				min="0"
				bind:value={form.season}
				oninput={onfieldchange}
			/>
		</div>
		<div class="field">
			<label class="field-label" for="{uid}-disc">Disc</label>
			<input
				id="{uid}-disc"
				class="field-control"
				type="number"
				min="1"
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
			{busy && !preview ? 'Previewing…' : 'Preview'}
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
