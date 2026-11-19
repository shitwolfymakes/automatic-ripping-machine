<script lang="ts">
	// An on/off setting as a switch that saves on change (no Save button), such
	// as the notifications master switch or Defaults' auto-apply. The caller saves.
	import Toggle from '$lib/components/shared/Toggle.svelte';
	import FieldLabel from '$lib/components/shared/FieldLabel.svelte';

	let {
		key,
		label,
		help,
		checked,
		ontoggle
	}: { key: string; label: string; help?: string | null; checked: boolean; ontoggle: (next: boolean) => void } =
		$props();
</script>

<div class="stack stack-sm" id="setting-{key}" data-testid="setting-{key}">
	<div class="field field-row auto-save-toggle-row">
		<Toggle id="toggle-{key}" {checked} {label} onchange={ontoggle} />
		<FieldLabel for="toggle-{key}" {label} docsId={`config.${key}`} />
		<span class="auto-save-toggle-hint">(changes save automatically)</span>
	</div>
	{#if help}<p class="field-help">{help}</p>{/if}
</div>

<style>
	.auto-save-toggle-row {
		gap: 0.75rem;
	}
	.auto-save-toggle-hint {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-muted);
	}
</style>
