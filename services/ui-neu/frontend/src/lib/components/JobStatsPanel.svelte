<script lang="ts" module>
	// v3 has no job-stats endpoint (fetchJobStats is MISSING and rejects), and
	// the BFF's JobStats interface was removed from $lib/api/jobs. Declare it
	// locally so this panel still type-checks; the feature is effectively dead
	// until a v3 stats endpoint exists.
	export interface JobStats {
		total: number;
		active: number;
		success: number;
		fail: number;
		waiting: number;
	}
</script>

<script lang="ts">
	interface Props {
		stats?: JobStats;
		statusFilter: string;
		onfilter: (value: string) => void;
	}

	let { stats, statusFilter, onfilter }: Props = $props();

	// Five statuses, four tones (danger/warning/success/info) plus a neutral
	// "total" tile with no tone of its own - the vocabulary has no fifth hue,
	// so `total` maps to `stat-muted` rather than inventing one. The original's
	// left accent stripe carries a matching CSS var per tile.
	const cards = [
		{ key: 'total' as const, label: 'Total', filter: '', tone: 'stat-muted', accent: 'var(--color-text-secondary)' },
		{ key: 'active' as const, label: 'Active', filter: 'active', tone: 'stat-info', accent: 'var(--color-info)' },
		{ key: 'success' as const, label: 'Success', filter: 'success', tone: 'stat-success', accent: 'var(--color-success)' },
		{ key: 'fail' as const, label: 'Failed', filter: 'fail', tone: 'stat-danger', accent: 'var(--color-danger)' },
		{ key: 'waiting' as const, label: 'Waiting', filter: 'waiting', tone: 'stat-warning', accent: 'var(--color-warning)' }
	];
</script>

<div class="cluster">
	{#each cards as card}
		<button
			onclick={() => onfilter(card.filter)}
			class="stat {card.tone} job-stats-panel-tile"
			style:--accent={card.accent}
			aria-pressed={statusFilter === card.filter}
		>
			<div class="stat-value">{stats ? stats[card.key] : '-'}</div>
			<div class="stat-label">{card.label}</div>
		</button>
	{/each}
</div>

<style>
	/* stat is a static tile; this one is a clickable filter button, so it
	   keeps stat's look but adds the button affordances the original had
	   (min width, flex growth, left accent stripe, hover elevation, selected
	   ring) */
	.job-stats-panel-tile {
		display: block;
		min-width: 120px;
		flex: 1 1 0%;
		cursor: pointer;
		text-align: left;
		border-left: 4px solid var(--accent);
		transition: box-shadow var(--motion-fast) var(--ease);
	}
	.job-stats-panel-tile:hover { box-shadow: var(--shadow-2); }
	.job-stats-panel-tile[aria-pressed="true"] { box-shadow: 0 0 0 2px color-mix(in srgb, var(--color-primary) 40%, transparent); }
</style>
