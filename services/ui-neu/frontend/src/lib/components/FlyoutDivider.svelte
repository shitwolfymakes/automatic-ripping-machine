<script lang="ts">
	interface Props {
		/** Optional section label rendered as a small heading instead of a plain rule. */
		label?: string;
	}
	let { label }: Props = $props();
</script>

{#if label}
	<div class="px-3 py-1.5 text-xs font-semibold text-gray-400 dark:text-gray-500">{label}</div>
{:else}
	<div class="my-1 border-t border-primary/10 dark:border-primary/20"></div>
{/if}
