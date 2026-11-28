<script lang="ts">
	import type { IdentifyMatch } from '$lib/types/api.gen';
	import { matchExplanation } from '$lib/jobs/match-explain';

	interface Props {
		match: IdentifyMatch | null;
	}

	let { match }: Props = $props();

	let why = $derived(matchExplanation(match));
</script>

{#if why && match}
	<details class="match-why" data-testid="match-why">
		<summary>Why this match</summary>
		{#if match.text_disagrees}
			<p class="alert alert-warning mt-2" role="note">The disc's text and runtime don't look like this title.</p>
		{/if}
		<ul class="match-why-parts" aria-label="Score by part">
			{#each why.parts as part (part.label)}
				<li><strong>{part.label}</strong> {part.points}, {part.detail}</li>
			{/each}
		</ul>
		<ul class="match-why-evidence" aria-label="Evidence used">
			{#each why.evidence as line (line)}
				<li>{line}</li>
			{/each}
		</ul>
	</details>
{/if}

<style>
	.match-why summary {
		cursor: pointer;
		color: var(--color-primary-text);
		font-weight: 600;
	}
	.match-why-parts,
	.match-why-evidence {
		display: grid;
		gap: 0.25rem;
		margin-top: 0.5rem;
		padding-left: 1.25rem;
		font-size: 0.8125rem;
		color: var(--color-text-muted);
	}
</style>
