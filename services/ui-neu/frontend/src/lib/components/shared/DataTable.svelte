<script lang="ts" generics="R">
	// A read-only table: the columns say what each cell shows, the actions
	// snippet draws the last cell of every row. The wrapper scrolls sideways
	// in a narrow window, never the page.
	import type { Snippet } from 'svelte';
	import MediaPill from '$lib/components/shared/MediaPill.svelte';
	import type { MediaType } from '$lib/types/api.gen';
	import { alignClass, cellView, type BadgeTone, type TableColumn } from '$lib/ui/data-table';

	interface Props {
		columns: TableColumn<R>[];
		rows: R[];
		rowKey: (row: R) => string;
		activeKey?: string | null;
		label: string;
		actions: Snippet<[R]>;
		empty?: string;
	}

	const BADGE_CLASS: Record<BadgeTone, string> = {
		warn: 'badge badge-sm badge-warning',
		info: 'badge badge-sm badge-info',
		neutral: 'badge badge-sm'
	};

	let { columns, rows, rowKey, activeKey = null, label, actions, empty }: Props = $props();
</script>

<div class="data-table-scroll">
	<table class="data-table" aria-label={label}>
		<thead>
			<tr>
				{#each columns as col (col.id)}
					<th scope="col" class={alignClass(col.align)}>{col.header}</th>
				{/each}
				<th scope="col" class="data-table-actions"><span class="sr-only">Actions</span></th>
			</tr>
		</thead>
		<tbody>
			{#each rows as row (rowKey(row))}
				<tr aria-current={rowKey(row) === activeKey ? 'true' : undefined}>
					{#each columns as col (col.id)}
						{@const view = cellView(col.cell(row), col.align)}
						<td class={view.className} data-muted={view.muted}>
							<div class="data-table-main">
								{#if view.pill?.kind === 'media'}
									<MediaPill mediaType={view.pill.tone as MediaType} />
								{:else if view.pill}
									<span class="badge badge-sm data-table-tag" data-tone={view.pill.tone} title={view.pill.text}
										>{view.pill.text}</span
									>
								{:else}
									<span class={view.textClass} title={view.title}>{view.text}</span>
								{/if}
								{#each view.badges ?? [] as badge (badge.text)}
									<span class={BADGE_CLASS[badge.tone]} title={badge.text}>{badge.text}</span>
								{/each}
							</div>
							{#if view.sub}<div class="data-table-sub" title={view.sub}>{view.sub}</div>{/if}
						</td>
					{/each}
					<td class="data-table-actions">{@render actions(row)}</td>
				</tr>
			{:else}
				{#if empty}
					<tr>
						<td class="data-table-empty" colspan={columns.length + 1}>{empty}</td>
					</tr>
				{/if}
			{/each}
		</tbody>
	</table>
</div>

<style>
	.data-table-scroll {
		overflow-x: auto;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		background: var(--color-surface);
	}
	.data-table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.8125rem;
	}
	.data-table tr {
		background: var(--color-surface);
	}
	.data-table th {
		padding: 0.625rem 0.75rem;
		text-align: left;
		font-size: 0.6875rem;
		font-weight: 400;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		white-space: nowrap;
		color: var(--color-text-muted);
	}
	.data-table td {
		max-width: 12rem;
		padding: 0.5rem 0.75rem;
		border-top: 1px solid var(--color-border);
		color: var(--color-text);
		vertical-align: middle;
	}
	.data-table td:first-child {
		font-size: 0.875rem;
		font-weight: 600;
	}
	.data-table-tag {
		flex-shrink: 0;
		padding: 0.125rem 0.375rem;
		font-size: 0.75rem;
		line-height: 1rem;
		font-weight: 700;
		letter-spacing: 0.1em;
		text-transform: uppercase;
	}
	.data-table-tag[data-tone='builtin'] {
		background: var(--color-warning-soft);
		color: var(--color-on-warning-soft);
	}
	.data-table-tag[data-tone='custom'] {
		background: var(--color-info-soft);
		color: var(--color-on-info-soft);
	}
	.data-table tr[aria-current='true'] {
		background: linear-gradient(var(--color-primary-tint-2), var(--color-primary-tint-2)), var(--color-surface);
	}
	.data-table td[data-muted='true'] {
		color: var(--color-text-muted);
	}
	.data-table .data-table-num {
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
	.data-table-main {
		display: flex;
		min-width: 0;
		align-items: center;
		gap: 0.5rem;
	}
	.data-table-text {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.data-table-sub {
		margin-top: 0.125rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}
	/* Pinned to the right edge so the actions stay reachable when a narrow
	   window scrolls the table sideways; the cell takes its row's background. */
	.data-table .data-table-actions {
		position: sticky;
		right: 0;
		max-width: none;
		background: inherit;
		white-space: nowrap;
		text-align: right;
	}
	.data-table td.data-table-empty {
		max-width: none;
		padding: 1rem;
		text-align: center;
		color: var(--color-text-faint);
	}
</style>
