<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		onclick: () => void;
		/** Optional leading icon. */
		icon?: Snippet;
		/** Visually mark a destructive action (red text). */
		danger?: boolean;
		disabled?: boolean;
		children: Snippet;
	}

	let { onclick, icon, danger = false, disabled = false, children }: Props = $props();
</script>

<button
	type="button"
	role="menuitem"
	{onclick}
	{disabled}
	class="flyout-item"
	data-danger={danger}
>
	{#if icon}
		<span class="shrink-0 flyout-item-icon">{@render icon()}</span>
	{/if}
	{@render children()}
</button>

<style>
	/* flyout.css's .flyout-item covers layout/hover/disabled; the danger tone
	   and icon-slot colour are FlyoutItem-specific additions. */
	.flyout-item[data-danger="true"] {
		color: var(--color-danger);
	}
	.flyout-item[data-danger="true"]:hover {
		background: var(--color-danger-soft);
	}
	.flyout-item-icon {
		color: var(--color-text-faint);
	}
</style>
