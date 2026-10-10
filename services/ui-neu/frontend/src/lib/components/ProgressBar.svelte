<script lang="ts">
	interface Props {
		value: number;
		max?: number;
		/** CSS colour value (e.g. a var(--color-status-*) reference) overriding
		 * the fill's default --color-primary. */
		colorVar?: string | null;
		showLabel?: boolean;
	}

	let { value, max = 100, colorVar = null, showLabel = true }: Props = $props();
	let pct = $derived(Math.min(100, Math.max(0, (value / max) * 100)));
</script>

<div class="progress-bar-row">
	<div class="progress flex-1">
		<div data-progress-track class="progress-track">
			<div
				data-progress-fill
				class="progress-fill"
				style:--progress="{pct}%"
				style:--progress-color={colorVar || undefined}
			></div>
		</div>
	</div>
	{#if showLabel}
		<span class="progress-bar-label">{Math.round(pct)}%</span>
	{/if}
</div>

<style>
	.progress-bar-row { display: flex; align-items: center; gap: 0.5rem; }
	.progress-bar-label { min-width: 3ch; text-align: right; font-size: 0.75rem; color: var(--color-text-muted); }
</style>
