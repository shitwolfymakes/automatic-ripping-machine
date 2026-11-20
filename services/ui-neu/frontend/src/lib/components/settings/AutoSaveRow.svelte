<script lang="ts">
	// The row shared by the settings that save on change (no Save button): the
	// `setting-<key>` anchor, the control passed as children, the auto-save hint
	// and the help line. The caller saves.
	import type { Snippet } from 'svelte';

	let { key, help, children }: { key: string; help?: string | null; children: Snippet } = $props();
</script>

<div class="stack stack-sm" id="setting-{key}" data-testid="setting-{key}">
	<div class="field field-row auto-save-row">
		{@render children()}
		<span class="auto-save-row-hint">(changes save automatically)</span>
	</div>
	{#if help}<p class="field-help">{help}</p>{/if}
</div>

<style>
	.auto-save-row {
		gap: 0.75rem;
	}
	.auto-save-row-hint {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-muted);
	}
</style>
