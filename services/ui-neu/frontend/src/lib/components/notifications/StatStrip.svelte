<script lang="ts">
	let { total, issues, subscribedEvents }: { total: number; issues: number; subscribedEvents: number } = $props();
	const issueTone = $derived(issues > 0 ? 'stat-danger' : 'stat-success');
</script>

<div class="grid-3 stat-strip">
	<div class="stat">
		<p class="stat-label">Channels</p>
		<p class="stat-value">{total}</p>
	</div>
	<div class="stat {issueTone}">
		<p class="stat-label">Issues</p>
		<p class="stat-value">{issues}</p>
	</div>
	<div class="stat stat-muted">
		<p class="stat-label">Subscribed events</p>
		<p class="stat-value">{subscribedEvents}</p>
	</div>
</div>

<style>
	/* grid-3's 1rem gap is wider than this strip's original gap-3 (0.75rem). */
	.stat-strip { gap: 0.75rem; }
	/* the .stat block defaults to --color-surface; this strip's tiles were
	   always the slightly more tinted --color-page instead. */
	.stat-strip .stat { background: var(--color-page); }
	/* the .stat block's value margin-top (0.5rem) is sized for a future denser
	   consumer (JobStatsPanel); this strip's value sat closer to its label
	   (mt-1, 0.25rem). */
	.stat-strip .stat-value { margin-top: 0.25rem; }
</style>
