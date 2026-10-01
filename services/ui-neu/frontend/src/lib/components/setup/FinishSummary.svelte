<script lang="ts">
	import type { SetupView } from '$lib/types/api.gen';
	import Glyph from '$lib/components/Glyph.svelte';
	import { STEPS } from './steps';

	// One row per step: what was set up, with a way back to it. Used by the
	// walkthrough's Finish step.
	let { view, summaries = {} }: { view: SetupView; summaries?: Record<string, string> } = $props();

	const rows = $derived(STEPS.filter((s) => s.id !== 'finish'));
	function state(id: string): 'done' | 'skipped' | 'attention' | 'pending' {
		const s = view.progress[id]?.state;
		return s === 'done' || s === 'skipped' || s === 'attention' ? s : 'pending';
	}
	const BADGE = {
		done: { text: 'Done', glyph: 'check', cls: 'chip-success' },
		skipped: { text: 'Skipped', glyph: 'minus-circle', cls: '' },
		attention: { text: 'Needs attention', glyph: 'warning', cls: 'chip-warning' },
		pending: { text: 'Not done', glyph: 'clock', cls: '' }
	} as const;
</script>

<ul class="finish-summary">
	{#each rows as r (r.id)}
		{@const st = state(r.id)}
		{@const b = BADGE[st]}
		<li class="finish-summary-row" data-testid="finish-row-{r.id}" data-state={st}>
			<span class="chip chip-sm {b.cls} finish-summary-badge"><Glyph name={b.glyph} class="h-3 w-3" />{b.text}</span>
			<span class="finish-summary-main">
				<span class="finish-summary-label">{r.label}</span>
				{#if summaries[r.id]}<span class="finish-summary-text">{summaries[r.id]}</span>{/if}
			</span>
			<a class="btn btn-sm" href="/setup/{r.id}" aria-label="Edit {r.label}">Edit</a>
		</li>
	{/each}
</ul>

<style>
	.finish-summary {
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.finish-summary-row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 0.75rem;
		border-top: 1px solid var(--color-border);
		padding: 0.75rem 0;
	}
	.finish-summary-badge {
		flex: none;
		min-width: 7.5rem;
		justify-content: center;
	}
	.finish-summary-main {
		display: grid;
		flex: 1 1 14rem;
		min-width: 0;
	}
	.finish-summary-label {
		font-weight: 600;
	}
	.finish-summary-text {
		font-size: 0.8125rem;
		color: var(--color-text-muted);
	}
</style>
