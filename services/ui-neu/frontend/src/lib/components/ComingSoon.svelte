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
		class="cursor-not-allowed rounded px-2 py-0.5 text-xs font-medium opacity-50 {klass}"
	>
		{label}
	</button>
	<span class="rounded-full bg-gray-200 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gray-500 dark:bg-gray-700 dark:text-gray-400">
		Coming soon
	</span>
</span>
