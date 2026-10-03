<script lang="ts">
	import Toggle from '../Toggle.svelte';

	let {
		name = $bindable(),
		enabled = $bindable()
	}: { name: string; enabled: boolean } = $props();
</script>

<div class="label-enabled-row">
	<label class="field">
		<span class="field-label">Channel Label *</span>
		<input aria-label="Channel Label" bind:value={name} required />
	</label>
	<div class="cluster label-enabled-row-toggle">
		<Toggle checked={enabled} label="Enabled" onchange={(v) => (enabled = v)} />
		<span class="label-enabled-row-toggle-label">Enabled</span>
	</div>
</div>

<style>
	.label-enabled-row { display: grid; grid-template-columns: 1fr auto; align-items: end; gap: 1rem; }
	.label-enabled-row-toggle { padding-bottom: 0.5rem; }
	.label-enabled-row-toggle-label { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-secondary); }
</style>
