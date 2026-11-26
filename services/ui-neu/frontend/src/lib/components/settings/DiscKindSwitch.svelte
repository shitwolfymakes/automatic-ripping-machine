<script lang="ts">
	import { DISC_KIND_LABELS, DISC_KINDS, type DiscKind } from '$lib/jobs/identity-card';

	// The Identity card's Preview control, a segmented radiogroup choosing the
	// disc kind the preview shows.
	let { kind = $bindable() }: { kind: DiscKind } = $props();
</script>

<div class="disc-kind-switch" role="radiogroup" aria-label="Disc kind">
	{#each DISC_KINDS as k (k)}
		<button type="button" role="radio" aria-checked={kind === k} class="disc-kind-switch-btn" onclick={() => (kind = k)}
			>{DISC_KIND_LABELS[k]}</button
		>
	{/each}
</div>

<style>
	/* Segmented radiogroup: one outlined group, the selected kind filled. */
	.disc-kind-switch {
		display: inline-flex;
		align-self: flex-start;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		overflow: hidden;
		background: transparent;
	}
	.disc-kind-switch-btn {
		padding: 0.5rem 1.125rem;
		font-size: 0.9375rem;
		font-weight: 500;
		line-height: 1.25rem;
		background: transparent;
		color: var(--color-text);
		cursor: pointer;
		transition:
			background-color var(--motion-fast) var(--ease),
			color var(--motion-fast) var(--ease);
	}
	.disc-kind-switch-btn + .disc-kind-switch-btn {
		border-left: 1px solid var(--color-border);
	}
	.disc-kind-switch-btn:hover {
		background: color-mix(in srgb, var(--color-primary) 8%, transparent);
	}
	.disc-kind-switch-btn[aria-checked='true'] {
		background: var(--color-primary);
		color: var(--color-primary-contrast, var(--color-on-primary));
	}
</style>
