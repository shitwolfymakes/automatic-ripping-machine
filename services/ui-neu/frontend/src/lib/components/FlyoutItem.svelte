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

	const tone = $derived(
		danger
			? 'text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20'
			: 'text-gray-700 hover:bg-primary/5 dark:text-gray-300 dark:hover:bg-primary/10'
	);
</script>

<button
	type="button"
	role="menuitem"
	{onclick}
	{disabled}
	class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50 {tone}"
>
	{#if icon}
		<span class="shrink-0 text-gray-400">{@render icon()}</span>
	{/if}
	{@render children()}
</button>
