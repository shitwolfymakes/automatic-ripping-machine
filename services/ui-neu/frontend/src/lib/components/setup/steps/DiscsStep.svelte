<script lang="ts">
	import { onMount } from 'svelte';
	import type { DiscRouteSummary, SetupView } from '$lib/types/api.gen';
	import RecipeStrip from '$lib/components/setup/RecipeStrip.svelte';
	import { fetchDiscRoutes } from '$lib/api/setup';
	import { discKindLabel, exampleMovie, routeCells } from '$lib/sessions/disc-routes';
	import SetupConfigFields from '../SetupConfigFields.svelte';
	import type { StepCommitResult } from '../../../setup/steps';

	// Step 6: the global "when you insert a disc" default (the disc_handling
	// widget) and, read-only, what each kind of disc gets (setup spec §5.7).
	let { view }: { view: SetupView; setBlocked?: (reason: string | null) => void } = $props();
	void view;
	let fields: SetupConfigFields | undefined = $state();
	let routes = $state<DiscRouteSummary[] | null>(null);

	onMount(async () => {
		try {
			routes = await fetchDiscRoutes();
		} catch {
			routes = [];
		}
	});

	export async function commit(): Promise<StepCommitResult> {
		if (!fields || !(await fields.save())) return false;
		return 'done';
	}
</script>

<div class="stack stack-lg">
	<SetupConfigFields bind:this={fields} step="discs" />

	<section class="panel stack" data-testid="disc-routes">
		<div>
			<h2 class="discs-step-title">What happens to each kind of disc</h2>
			<p class="discs-step-help">ARM's sessions, read-only here.</p>
		</div>
		{#if routes === null}
			<p class="discs-step-help">Loading...</p>
		{:else}
			{@const example = exampleMovie(routes)}
			{#each routes as r (r.kind)}
				<div class="discs-step-row">
					<span class="badge badge-sm discs-step-kind">{discKindLabel(r.kind)}</span>
					<RecipeStrip cells={routeCells(r)} />
				</div>
			{/each}
			{#if example}
				<div class="discs-step-example">
					<span class="discs-step-example-label">Example movie</span>
					<code class="mono">{example}</code>
				</div>
			{/if}
		{/if}
		<p class="discs-step-help">You can change these later in Settings, Sessions.</p>
	</section>
</div>

<style>
	.discs-step-title {
		font-size: 1.0625rem;
		font-weight: 600;
	}
	.discs-step-help {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
	.discs-step-row {
		display: grid;
		gap: 0.375rem;
	}
	.discs-step-kind {
		justify-self: start;
	}
	.discs-step-example {
		display: grid;
		gap: 0.25rem;
		border-top: 1px solid var(--color-border);
		padding-top: 0.75rem;
		font-size: 0.8125rem;
		overflow-wrap: anywhere;
	}
	.discs-step-example-label {
		font-size: 0.75rem;
		font-weight: 600;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: var(--color-text-faint);
	}
</style>
