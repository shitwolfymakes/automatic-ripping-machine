<script lang="ts">
	// The Match Episodes rows (design spec 2026-10-02 section 4.2): a table on
	// desktop, stacked cards below 640px. Presentational only - the panel owns
	// the data and the actions.
	import { SOURCE_LABEL, type EpisodeRow } from './episodeModel';

	interface FileName {
		name: string;
		path: string;
	}
	interface Props {
		rows: EpisodeRow[];
		fileNames: Map<string, FileName>;
		matching?: boolean;
		phone?: boolean;
		/** Label of the source being previewed; null when no preview is shown. */
		proposedLabel?: string | null;
		/** Set-by-hand choices; null hides the pickers and Revert (guest, matching, preview). */
		options?: { value: string; label: string }[] | null;
		onpick?: (trackId: string, value: string) => void;
		onrevert?: (trackId: string) => void;
	}
	let {
		rows,
		fileNames,
		matching = false,
		phone = false,
		proposedLabel = null,
		options = null,
		onpick,
		onrevert
	}: Props = $props();

	function pick(trackId: string, e: Event & { currentTarget: HTMLSelectElement }) {
		const value = e.currentTarget.value;
		e.currentTarget.value = '';
		if (value) onpick?.(trackId, value);
	}

	const ORIGIN_CHIP = { auto: 'chip-info', suggestion: 'chip-warning', you: '', none: '' } as const;

	function originLabel(row: EpisodeRow): string {
		const label = SOURCE_LABEL[row.origin.source ?? ''] ?? row.origin.source ?? '';
		if (row.origin.kind === 'auto') return `Auto · ${label}`;
		if (row.origin.kind === 'suggestion') return `Suggestion · ${label}`;
		if (row.origin.kind === 'you') return 'Set by you';
		return '—';
	}
	const conf = (c: number | null) => (c == null ? '—' : c.toFixed(2));
</script>

{#snippet placement(row: EpisodeRow)}
	{#if matching}
		<span class="episode-rows-muted">Waiting for matcher</span>
	{:else if phone && proposedLabel && row.changed && row.proposed}
		<s class="episode-rows-old"
			><span class="episode-rows-code">{row.code}</span>
			{#if row.name}<span class="episode-rows-name">{row.name}</span>{/if}</s
		>
		<span class="episode-rows-proposed">{@render proposal(row.proposed)}</span>
	{:else}
		<span class="episode-rows-code">{row.code}</span>
		{#if row.name}<span class="episode-rows-name">{row.name}</span>{/if}
	{/if}
	{#if fileNames.get(row.trackId)}
		{@const file = fileNames.get(row.trackId)}
		<span class="episode-rows-file" title={file?.path}>{file?.name}</span>
	{/if}
{/snippet}

{#snippet proposal(p: { code: string; name: string })}
	<span class="episode-rows-code">{p.code}</span>
	{#if p.name}<span class="episode-rows-name">{p.name}</span>{/if}
	<span class="chip chip-sm chip-warning">CHANGED</span>
{/snippet}

{#snippet byHand(row: EpisodeRow)}
	{#if options}
		<div class="episode-rows-hand">
			<select
				class="field-control episode-rows-select"
				aria-label="Set placement for {row.ref}"
				onchange={(e) => pick(row.trackId, e)}
			>
				<option value="">Change…</option>
				{#each options as o (o.value)}
					<option value={o.value}>{o.label}</option>
				{/each}
			</select>
			{#if row.handSet}
				<button type="button" class="btn btn-ghost btn-sm episode-rows-revert" onclick={() => onrevert?.(row.trackId)}
					>Revert</button
				>
			{/if}
		</div>
	{/if}
{/snippet}

{#snippet origin(row: EpisodeRow)}
	{#if matching || row.origin.kind === 'none'}
		<span class="episode-rows-muted">—</span>
	{:else}
		<span
			class="chip chip-sm {ORIGIN_CHIP[row.origin.kind]}"
			data-origin={row.origin.kind === 'you' ? 'you' : undefined}>{originLabel(row)}</span
		>
	{/if}
{/snippet}

{#if phone}
	<ul class="episode-rows-cards">
		{#each rows as row (row.trackId)}
			<li class="episode-rows-card">
				<div class="episode-rows-card-head">
					<span class="episode-rows-ref">{row.ref}</span>
					<span class="episode-rows-muted tabular-nums">{row.length}</span>
					<span class="episode-rows-card-origin">{@render origin(row)}</span>
				</div>
				<div class="episode-rows-placement">{@render placement(row)}</div>
				{#if !matching && row.confidence != null}
					<span class="episode-rows-muted">Confidence {conf(row.confidence)}</span>
				{/if}
				{@render byHand(row)}
			</li>
		{/each}
	</ul>
{:else}
	<div class="overflow-x-auto">
		<table class="table table-compact episode-rows-table">
			<thead>
				<tr>
					<th class="table-header">Track</th>
					<th class="table-header">Length</th>
					<th class="table-header">Placement</th>
					{#if proposedLabel}<th class="table-header">Proposed · {proposedLabel}</th>{/if}
					<th class="table-header">Origin</th>
					<th class="table-header table-right">Conf.</th>
					{#if options}<th class="table-header">Set by hand</th>{/if}
				</tr>
			</thead>
			<tbody>
				{#each rows as row (row.trackId)}
					<tr class="table-row">
						<td class="table-cell episode-rows-ref">{row.ref}</td>
						<td class="table-cell tabular-nums">{row.length}</td>
						<td class="table-cell"><div class="episode-rows-placement">{@render placement(row)}</div></td>
						{#if proposedLabel}
							<td class="table-cell" data-changed={row.changed}>
								{#if row.proposed && row.changed}
									<div class="episode-rows-placement episode-rows-proposed">{@render proposal(row.proposed)}</div>
								{:else if row.proposed}
									<span class="episode-rows-muted">Same</span>
								{:else}
									<span class="episode-rows-muted">—</span>
								{/if}
							</td>
						{/if}
						<td class="table-cell">{@render origin(row)}</td>
						<td class="table-cell table-right tabular-nums">{matching ? '—' : conf(row.confidence)}</td>
						{#if options}<td class="table-cell">{@render byHand(row)}</td>{/if}
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}

<style>
	.episode-rows-table {
		width: 100%;
	}
	.episode-rows-ref {
		font-family: var(--font-mono);
		font-size: 0.8125rem;
	}
	.episode-rows-placement {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		column-gap: 0.375rem;
		min-width: 0;
	}
	.episode-rows-code {
		font-weight: 700;
	}
	.episode-rows-name {
		color: var(--color-text-secondary);
	}
	.episode-rows-file {
		flex-basis: 100%;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-family: var(--font-mono);
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}
	.episode-rows-old {
		display: flex;
		flex-wrap: wrap;
		column-gap: 0.375rem;
		color: var(--color-text-muted);
	}
	.episode-rows-proposed {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		column-gap: 0.375rem;
	}
	td[data-changed='true'] {
		background: var(--color-warning-soft);
	}
	.episode-rows-hand {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		min-width: 0;
	}
	.episode-rows-select {
		min-width: 0;
		max-width: 16rem;
	}
	.episode-rows-card .episode-rows-hand {
		flex-wrap: wrap;
	}
	.episode-rows-card .episode-rows-select {
		flex: 1 1 100%;
		max-width: none;
		min-height: 2.75rem;
	}
	.episode-rows-card .episode-rows-revert {
		min-height: 2.75rem;
	}
	.episode-rows-muted {
		color: var(--color-text-muted);
		font-size: 0.8125rem;
	}
	.episode-rows-cards {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}
	.episode-rows-card {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		min-width: 0;
		padding: 0.625rem 0.75rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-surface-raised);
	}
	.episode-rows-card-head {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.episode-rows-card-origin {
		margin-left: auto;
	}
</style>
