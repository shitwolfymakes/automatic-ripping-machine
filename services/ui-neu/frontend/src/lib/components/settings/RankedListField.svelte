<script lang="ts">
	import { tick } from 'svelte';
	import Glyph from '$lib/components/Glyph.svelte';
	import type { ConfigFieldMeta } from '$lib/types/api.gen';

	let {
		field,
		value = $bindable(),
		config = {}
	}: { field: ConfigFieldMeta; value: unknown; config?: Record<string, unknown> } = $props();

	const known = $derived(field.enum_values ?? []);
	const selected = $derived(
		Array.isArray(value) ? (value as string[]).filter((v, i, all) => known.includes(v) && all.indexOf(v) === i) : []
	);
	const rows = $derived([...selected, ...known.filter((v) => !selected.includes(v))]);
	let announcement = $state('');

	const labelOf = (v: string) => field.enum_labels?.[v] ?? v;
	function missingKey(v: string): string | null {
		const key = field.enum_requires?.[v];
		if (!key) return null;
		const current = config[key];
		return typeof current === 'string' && current.trim() !== '' ? null : key;
	}
	const buttonId = (v: string, dir: 'up' | 'down') => `ranked-${field.key}-${v}-${dir}`;
	const rankId = (v: string) => `ranked-${field.key}-${v}-rank`;

	function toggle(v: string, on: boolean) {
		value = on ? [...selected, v] : selected.filter((s) => s !== v);
	}

	async function move(v: string, dir: 'up' | 'down') {
		const i = selected.indexOf(v);
		const j = dir === 'up' ? i - 1 : i + 1;
		if (i < 0 || j < 0 || j >= selected.length) return;
		const next = [...selected];
		[next[i], next[j]] = [next[j], next[i]];
		value = next;
		// Clear first: reassigning $state to an identical string is a no-op
		// as far as the DOM text node is concerned, so back-to-back moves that
		// land on the same wording would otherwise go unannounced.
		announcement = '';
		await tick();
		announcement = `${labelOf(v)} moved to rank ${j + 1}`;
		await tick();
		const same = document.getElementById(buttonId(v, dir)) as HTMLButtonElement | null;
		const other = document.getElementById(buttonId(v, dir === 'up' ? 'down' : 'up')) as HTMLButtonElement | null;
		(same && !same.disabled ? same : other)?.focus();
	}
</script>

<div class="ranked-list-field-list" role="list" aria-label={field.label}>
	{#each rows as v (v)}
		{@const isOn = selected.includes(v)}
		{@const rank = selected.indexOf(v)}
		{@const missing = missingKey(v)}
		<div class="list-row list-row-compact ranked-list-field-row" role="listitem" data-on={isOn}>
			<div class="list-row-lead">
				<input
					type="checkbox"
					checked={isOn}
					aria-label={`Use ${labelOf(v)}`}
					aria-describedby={rankId(v)}
					onchange={(e) => toggle(v, (e.currentTarget as HTMLInputElement).checked)}
				/>
			</div>
			<div class="list-row-main">
				<div class="ranked-list-field-name">{labelOf(v)}</div>
				<div id={rankId(v)} class="ranked-list-field-rank">
					<span>{isOn ? `Rank ${rank + 1}` : 'Not used'}</span>
					{#if missing}
						<a class="chip chip-warning chip-sm" href="#Metadata/{missing}">
							<Glyph name="warning" />
							Needs {labelOf(v)} key
						</a>
					{/if}
				</div>
			</div>
			{#if isOn}
				<div class="list-row-actions ranked-list-field-actions">
					<button
						id={buttonId(v, 'up')}
						type="button"
						class="btn btn-icon ranked-list-field-move"
						aria-label={`Move ${labelOf(v)} up`}
						disabled={rank === 0}
						onclick={() => move(v, 'up')}
					>
						<Glyph name="chevron-up" />
					</button>
					<button
						id={buttonId(v, 'down')}
						type="button"
						class="btn btn-icon ranked-list-field-move"
						aria-label={`Move ${labelOf(v)} down`}
						disabled={rank === selected.length - 1}
						onclick={() => move(v, 'down')}
					>
						<Glyph name="chevron-down" />
					</button>
				</div>
			{/if}
		</div>
	{/each}
</div>
<div class="sr-only" aria-live="polite">{announcement}</div>

<style>
	.ranked-list-field-list {
		max-width: 36rem;
	}
	.ranked-list-field-row {
		/* the list owns the column template: checkbox, name + rank (grows),
		   actions. Off rows simply leave the actions column empty. */
		grid-template-columns: auto 1fr auto;
		/* rows are not clickable; only their controls are - undo list-row's
		   hover tint and pointer cursor. */
		cursor: default;
	}
	.ranked-list-field-row:hover {
		background: transparent;
	}
	.ranked-list-field-row[data-on='false'] .ranked-list-field-name {
		color: var(--color-text-muted);
	}
	/* two classes so this reliably beats list-row.css's
	   `.list-row-main > :nth-child(2)` (same specificity, but that rule's
	   nowrap/ellipsis would stop the chip from wrapping under the rank). */
	.list-row-main > .ranked-list-field-rank {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.375rem;
		overflow: visible;
		text-overflow: clip;
		white-space: normal;
	}
	.ranked-list-field-actions {
		gap: 0.25rem;
	}
	.ranked-list-field-move {
		/* scoped minimum hit area, per the design's 44px targets */
		min-width: 2.75rem;
		min-height: 2.75rem;
	}
	@media (max-width: 30rem) {
		.ranked-list-field-actions {
			flex-direction: column;
		}
	}
</style>
