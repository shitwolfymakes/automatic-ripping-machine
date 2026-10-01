<script lang="ts">
	import { onMount } from 'svelte';
	import ChoiceCard from '$lib/components/ChoiceCard.svelte';
	import { fetchDrives } from '$lib/api/drives';

	// "When you insert a disc": one three-way choice over two config keys
	// (auto_rip_on_insert + hold_for_review). The global default each drive
	// follows unless it has its own mode (setup spec D1). Rendered by
	// SchemaConfigForm for the `disc_handling` widget, in Settings > Ripping and
	// in the setup walkthrough. `values` is the live form state it writes into.
	let { values, context = {} }: { values: Record<string, unknown>; context?: Record<string, unknown> } = $props();

	const waitSeconds = $derived(Number(values.manual_wait_seconds ?? context.manual_wait_seconds ?? 60) || 60);
	const current = $derived(
		values.auto_rip_on_insert === false ? 'manual' : values.hold_for_review === true ? 'review' : 'auto'
	);
	const options = $derived([
		{ value: 'auto', title: 'Fully automatic', description: 'Insert a disc and ARM identifies, rips and files it.' },
		{
			value: 'review',
			title: 'Review first',
			badge: 'Suggested',
			description: `ARM identifies the disc, then waits ${waitSeconds} seconds for you to check the title before ripping. No answer and it rips anyway.`
		},
		{ value: 'manual', title: 'Manual', description: 'Nothing starts until you press Start.' }
	]);

	function choose(v: string) {
		if (v === 'manual') {
			values.auto_rip_on_insert = false;
			return;
		}
		values.auto_rip_on_insert = true;
		values.hold_for_review = v === 'review';
	}

	let overrides = $state(0);
	onMount(async () => {
		try {
			overrides = (await fetchDrives()).filter((d) => d.lifecycle === 'enrolled' && d.drive_mode != null).length;
		} catch {
			overrides = 0;
		}
	});
</script>

<div class="disc-handling-field stack">
	<div>
		<div class="field-label disc-handling-field-title">When you insert a disc</div>
		<p class="field-help">Applies to every drive. You can change it per drive later.</p>
	</div>
	<ChoiceCard name="disc-handling" value={current} {options} onchange={choose} legend="When you insert a disc" />
	{#if overrides > 0}
		<p class="field-help" data-testid="disc-handling-overrides">
			{overrides === 1 ? '1 drive has its own setting and' : `${overrides} drives have their own setting and`} won't change.
		</p>
	{/if}
</div>

<style>
	.disc-handling-field {
		gap: 0.75rem;
	}
	.disc-handling-field-title {
		color: var(--color-text);
		font-weight: 600;
	}
</style>
