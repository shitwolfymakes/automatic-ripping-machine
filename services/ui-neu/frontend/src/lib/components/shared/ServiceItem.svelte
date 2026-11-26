<script lang="ts">
	// One service's card in System health, saying what it can do, where it
	// runs, and which of its parts pass.
	import type { SystemDiagnosticCheck } from '$lib/types/api.gen';
	import { locationLabel, serviceBadge, serviceDescription, serviceLabel } from '$lib/dashboard/system-health';
	import Glyph from '$lib/components/shared/Glyph.svelte';
	import HealthItem from './HealthItem.svelte';

	let { check }: { check: SystemDiagnosticCheck } = $props();

	const b = $derived(serviceBadge(check.status));
</script>

<HealthItem
	testid="system-health-service"
	status={check.status}
	name={serviceLabel(check.name)}
	description={serviceDescription(check)}
>
	{#snippet badge()}
		<span class="badge badge-sm badge-{b.tone}"><Glyph name={b.glyph} class="h-3 w-3" /> {b.text}</span>
	{/snippet}
	{#snippet chips()}
		{#if locationLabel(check)}<span class="chip chip-sm chip-info">{locationLabel(check)}</span>{/if}
		{#each check.details ?? [] as d (d.label)}
			<span class="chip chip-sm {d.ok ? 'chip-success' : 'chip-danger'}">
				<Glyph name={d.ok ? 'check' : 'x'} class="h-3 w-3" />{d.label}{d.ok ? '' : ': problem'}
			</span>
		{/each}
	{/snippet}
	{#if check.status !== 'ok' && check.detail}
		<p class="mono service-item-detail">{check.detail}</p>
	{/if}
</HealthItem>

<style>
	.service-item-detail {
		font-size: 0.75rem;
		color: var(--color-text-muted);
		overflow-wrap: anywhere;
	}
</style>
