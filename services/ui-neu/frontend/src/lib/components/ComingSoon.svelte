<script lang="ts">
	// Reusable "Coming soon" treatment for operator actions whose v3 backend
	// is not built yet. Renders a DISABLED button (so no handler fires) plus a
	// small "Coming soon" badge; the title tooltip names the feature. Single
	// source of truth — every deferred operator control uses this.
	let {
		label,
		feature = label,
		class: klass = ''
	}: { label: string; feature?: string; class?: string } = $props();
</script>

<span class="inline-flex items-center gap-1.5">
	<button
		type="button"
		disabled
		title={`${feature} - coming soon (not yet available in v3)`}
		class="coming-soon-btn {klass}"
	>
		{label}
	</button>
	<span class="badge badge-sm">
		Coming soon
	</span>
</span>

<style>
	.coming-soon-btn {
		padding: 0.125rem 0.5rem;
		border-radius: var(--radius-sm);
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--color-text-muted);
		opacity: 0.5;
	}
	.coming-soon-btn:disabled {
		cursor: not-allowed;
	}
</style>
