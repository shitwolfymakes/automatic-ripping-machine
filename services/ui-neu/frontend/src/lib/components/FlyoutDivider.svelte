<script lang="ts">
	interface Props {
		/** Optional section label rendered as a small heading instead of a plain rule. */
		label?: string;
	}
	let { label }: Props = $props();
</script>

{#if label}
	<div class="flyout-divider-label">{label}</div>
{:else}
	<div class="flyout-divider"></div>
{/if}

<style>
	.flyout-divider-label {
		padding: 0.375rem 0.75rem;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--color-text-faint);
	}
</style>
