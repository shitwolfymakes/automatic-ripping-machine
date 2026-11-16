<script lang="ts">
	import Toggle from '../../shared/Toggle.svelte';
	import FieldLabel from '../../shared/FieldLabel.svelte';
	import { FIELD_IDS } from '$lib/notifications/channel-form';

	let { name = $bindable(), enabled = $bindable() }: { name: string; enabled: boolean } = $props();
	const uid = $props.id();
</script>

<div class="label-enabled-row">
	<div class="field">
		<FieldLabel for="{uid}-label" label="Channel Label" docsId={FIELD_IDS.label} required />
		<input id="{uid}-label" aria-label="Channel Label" bind:value={name} required />
	</div>
	<div class="cluster label-enabled-row-toggle">
		<Toggle checked={enabled} label="Enabled" onchange={(v) => (enabled = v)} />
		<span class="label-enabled-row-toggle-label">Enabled</span>
	</div>
</div>

<style>
	.label-enabled-row {
		display: grid;
		grid-template-columns: 1fr auto;
		align-items: end;
		gap: 1rem;
	}
	.label-enabled-row-toggle {
		padding-bottom: 0.5rem;
	}
	.label-enabled-row-toggle-label {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-secondary);
	}
</style>
