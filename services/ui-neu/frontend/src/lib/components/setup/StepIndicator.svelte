<script lang="ts">
	interface Props {
		steps: { id: string; label: string }[];
		currentIndex: number;
	}

	let { steps, currentIndex }: Props = $props();
</script>

<nav class="step-indicator" aria-label="Setup progress">
	{#each steps as step, i}
		{#if i > 0}
			<div class="step-indicator-rule" data-active={i <= currentIndex}></div>
		{/if}
		<div class="step-indicator-item">
			<div
				class="step-indicator-dot"
				data-state={i < currentIndex ? 'done' : i === currentIndex ? 'current' : 'pending'}
			>
				{#if i < currentIndex}
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
					</svg>
				{:else}
					{i + 1}
				{/if}
			</div>
			<span class="hidden step-indicator-label sm:inline" data-active={i <= currentIndex}>
				{step.label}
			</span>
		</div>
	{/each}
</nav>

<style>
	.step-indicator { display: flex; align-items: center; justify-content: center; gap: 0.5rem; }
	.step-indicator-rule { height: 1px; width: 2rem; background: var(--color-border-strong); }
	.step-indicator-rule[data-active="true"] { background: var(--color-primary); }
	.step-indicator-item { display: flex; align-items: center; gap: 0.5rem; }
	.step-indicator-dot { display: flex; height: 2rem; width: 2rem; align-items: center; justify-content: center; border-radius: 9999px; font-size: 0.875rem; line-height: 1.25rem; font-weight: 500; transition: background-color var(--motion-fast) var(--ease), color var(--motion-fast) var(--ease); background: var(--color-primary-tint-3); color: var(--color-text-muted); }
	.step-indicator-dot[data-state="done"], .step-indicator-dot[data-state="current"] { background: var(--color-primary); color: var(--color-on-primary); }
	.step-indicator-dot[data-state="current"] { box-shadow: 0 0 0 2px color-mix(in srgb, var(--color-primary) 30%, transparent); }
	.step-indicator-label { font-size: 0.875rem; line-height: 1.25rem; font-weight: 500; color: var(--color-text-faint); }
	.step-indicator-label[data-active="true"] { color: var(--color-text); }
</style>
