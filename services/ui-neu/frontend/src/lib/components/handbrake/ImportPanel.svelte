<script lang="ts">
	import { errorMessage } from '$lib/utils/errors';
	// The HandBrake GUI export import flow in the preset sidebar: step 1 reads a
	// file or pasted JSON through the parse endpoint, step 2 reviews what came
	// back. Accepting hands the preset to the sidebar; nothing is saved here.
	import { parseHandbrakeImport } from '$lib/api/transcodePresets';
	import { TABS } from '$lib/handbrake/fields';
	import { defaultPick, reviewRows } from '$lib/handbrake/importReview';
	import { importPanelView } from '$lib/handbrake/importPanelView';
	import type { EncoderAvailabilityView, HandbrakeSchemaSlimView, ImportedPresetView } from '$lib/types/api.gen';

	interface Props {
		schema: HandbrakeSchemaSlimView | null;
		availability: EncoderAvailabilityView[];
		oncancel: () => void;
		onuse: (preset: ImportedPresetView) => void;
	}

	let { schema, availability, oncancel, onuse }: Props = $props();

	let text = $state('');
	let loading = $state(false);
	let error = $state<string | null>(null);
	let presets = $state<ImportedPresetView[] | null>(null);
	let pick = $state<number | null>(null);

	const picked = $derived(presets !== null && pick !== null ? presets[pick] : null);
	const view = $derived(importPanelView({ presets, schema, text, loading }));
	const review = $derived(picked && schema ? reviewRows(picked, schema, availability) : null);

	async function chooseFile(event: Event) {
		const file = (event.currentTarget as HTMLInputElement).files?.[0];
		if (file) text = await file.text();
	}

	async function readFile() {
		loading = true;
		error = null;
		try {
			const response = await parseHandbrakeImport(text);
			presets = response.presets;
			pick = defaultPick(response.presets);
		} catch (e) {
			error = errorMessage(e, 'Could not read the file');
		} finally {
			loading = false;
		}
	}
</script>

<div class="import-panel">
	{#if view.step === 1}
		<h3 class="import-title">Import a HandBrake preset</h3>
		<p class="import-steps">1. Import &gt; 2. Review</p>
		{#if view.showVersionLine}
			<p class="field-help">The file is checked against HandBrake {view.versionTag}, then discarded.</p>
		{/if}
		<p>Choose a preset file exported from the HandBrake app (Presets, Export), or paste its JSON.</p>
		<div class="import-field">
			<input
				id="import-file"
				class="sr-only import-file-input"
				type="file"
				accept="application/json,.json"
				onchange={chooseFile}
			/>
			<label class="btn btn-sm import-file-button" for="import-file">Choose file</label>
		</div>
		<div class="import-field">
			<label class="field-label" for="import-json">HandBrake preset JSON</label>
			<textarea id="import-json" class="field-control import-json" rows="8" bind:value={text}></textarea>
		</div>
		{#if error}<p class="field-error" role="alert">{error}</p>{/if}
		<p class="field-help">Nothing changes in the preset until you finish the review.</p>
		<div class="import-actions">
			<button type="button" class="btn btn-ghost" onclick={oncancel}>Cancel</button>
			<button type="button" class="btn btn-primary" disabled={!view.canRead} onclick={readFile}>{view.readLabel}</button
			>
		</div>
	{:else}
		<h3 class="import-title">Review the import</h3>
		{#if view.showPicks}
			<fieldset class="import-picks">
				<legend class="field-label">Preset in the file</legend>
				{#each view.picks as pickView, i (i)}
					<label class="import-pick">
						<input type="radio" name="import-pick" value={i} bind:group={pick} disabled={pickView.disabled} />
						<span>{pickView.label}</span>
						{#if pickView.reason}<span class="field-help">{pickView.reason}</span>{/if}
					</label>
				{/each}
			</fieldset>
		{:else if view.showSingleReason}
			<p class="field-error">{view.singleReason}</p>
		{/if}

		{#if review}
			<dl class="import-rows">
				<dt>Encoder in the file</dt>
				<dd>{review.encoderInFile}</dd>
				<dt>Codec and bit depth</dt>
				<dd>{review.codecDepth}</dd>
				<dt>Encoder in ARM</dt>
				<dd>{review.encoderInArm}</dd>
				<dt>Container</dt>
				<dd>{review.container}</dd>
			</dl>

			<h4 class="import-subtitle">{`Stored for ${review.storedFor}`}</h4>
			<dl class="import-rows">
				{#each review.values as [label, value] (label)}
					<dt>{label}</dt>
					<dd>{value}</dd>
				{/each}
			</dl>
			{#if review.copiedLine}<p>{review.copiedLine}</p>{/if}
			{#each review.eightBitOnly as line (line)}<p>{line}</p>{/each}

			<h4 class="import-subtitle">Settings stored</h4>
			<dl class="import-rows">
				{#each TABS as tab (tab.id)}
					<dt>{tab.label}</dt>
					<dd>{review.tabCounts[tab.id]}</dd>
				{/each}
				<dt>Total</dt>
				<dd>{review.total}</dd>
			</dl>
			<ul class="import-notes">
				{#each review.notes as note (note)}<li>{note}</li>{/each}
			</ul>
		{/if}

		<div class="import-actions">
			<button type="button" class="btn btn-ghost" onclick={() => (presets = null)}>Back</button>
			{#if picked}
				<button type="button" class="btn btn-primary" disabled={!picked.importable} onclick={() => onuse(picked)}
					>Use these settings</button
				>
			{:else}
				<button type="button" class="btn btn-primary" disabled>Use these settings</button>
			{/if}
		</div>
	{/if}
</div>

<style>
	.import-panel {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}
	.import-title,
	.import-subtitle {
		margin: 0;
	}
	.import-field {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}
	.import-steps {
		margin: 0;
		font-size: 0.75rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--color-text-muted);
	}
	.import-file-button {
		align-self: flex-start;
		cursor: pointer;
	}
	.import-file-input:focus-visible + .import-file-button {
		outline: 2px solid var(--color-primary);
		outline-offset: 2px;
	}
	.import-json {
		font-family: var(--font-mono, monospace);
	}
	.import-picks {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		border: 0;
		padding: 0;
	}
	.import-pick {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
	}
	.import-rows {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 0.25rem 1rem;
		margin: 0;
	}
	.import-rows dt {
		color: var(--color-text-secondary);
	}
	.import-rows dd {
		margin: 0;
	}
	.import-notes {
		margin: 0;
		padding-left: 1.5rem;
		list-style: disc;
		font-size: 0.875rem;
		color: var(--color-text-secondary);
	}
	.import-actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.75rem;
	}
</style>
