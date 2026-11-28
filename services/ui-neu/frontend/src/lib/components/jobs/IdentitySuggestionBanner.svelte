<script lang="ts">
	import type { JobView, ResolveResponse } from '$lib/types/api.gen';
	import { acceptIdentitySuggestion } from '$lib/api/jobs';
	import { saveErrorMessage } from '$lib/api/client';
	import { identitySuggestionOf } from '$lib/jobs/review';
	import { discRuntime, identifyMatchOf, shortlistRows } from '$lib/jobs/match-explain';
	import { providerLabel } from '$lib/settings/provider-labels';
	import PosterImage from '../shared/PosterImage.svelte';
	import MatchWhy from './MatchWhy.svelte';

	interface Props {
		job: JobView;
		canAct: boolean;
		onaccepted?: (resp: ResolveResponse) => void;
		onsearch?: () => void;
	}

	let { job, canAct, onaccepted, onsearch }: Props = $props();

	// A confident match identify held because the media type's auto-apply
	// switch is off. Accept applies it; Search hands off to the manual search.
	let suggestion = $derived(identitySuggestionOf(job));
	// A CD matched by track layout where several releases fit: the backend
	// ranked them, so this is the closest, but not the only, candidate.
	let tocCandidateCount = $derived.by(() => {
		const cands = (suggestion?.payload as { toc_candidates?: unknown } | undefined)?.toc_candidates;
		return Array.isArray(cands) ? cands.length : 0;
	});
	// Several close titles fit: the operator picks a row instead of confirming one match.
	let match = $derived(identifyMatchOf(job));
	let rows = $derived(suggestion?.reason === 'close' ? shortlistRows(suggestion, match) : []);
	let discMinutes = $derived(discRuntime(match));
	let accepting = $state(false);
	// The suggestion this banner accepted: its button stays disabled until the
	// parent's refresh drops the banner (a second accept would only get a 409).
	let acceptedSuggestion = $state.raw<typeof suggestion>(null);
	let errorMessage = $state<string | null>(null);

	async function accept(alternative?: number) {
		accepting = true;
		errorMessage = null;
		try {
			const accepted = suggestion;
			const resp =
				alternative === undefined
					? await acceptIdentitySuggestion(job.id)
					: await acceptIdentitySuggestion(job.id, alternative);
			acceptedSuggestion = accepted;
			onaccepted?.(resp);
		} catch (e) {
			errorMessage = saveErrorMessage(e);
		} finally {
			accepting = false;
		}
	}
</script>

{#snippet failure()}
	{#if errorMessage}
		<div class="alert alert-danger mt-2">{errorMessage}</div>
	{/if}
{/snippet}

{#if suggestion && rows.length > 0}
	<div class="identity-suggestion identity-suggestion-shortlist" data-testid="identity-shortlist">
		<div class="min-w-0 flex-1">
			<p class="identity-suggestion-heading">Several titles fit this disc</p>
			<p class="identity-suggestion-source">
				Pick the right one{discMinutes != null ? `; the disc runs ${Math.round(discMinutes)} min` : ''}.
			</p>
			<table class="table table-compact mt-2">
				<thead>
					<tr>
						<th class="table-header">Title</th>
						<th class="table-header">Kind</th>
						<th class="table-header table-right">Runtime</th>
						<th class="table-header table-right">Score</th>
						{#if canAct}<th class="table-header"><span class="sr-only">Use</span></th>{/if}
					</tr>
				</thead>
				<tbody>
					{#each rows as row (row.index)}
						<tr class="table-row" data-testid="shortlist-row">
							<td class="table-cell">
								{row.title}
								{#if row.note}<span class="identity-suggestion-source">, {row.note}</span>{/if}
							</td>
							<td class="table-cell">{row.kind}</td>
							<td class="table-cell table-right">{row.runtime}</td>
							<td class="table-cell table-right">{row.score}</td>
							{#if canAct}
								<td class="table-cell table-right">
									<button
										type="button"
										class="btn btn-primary btn-sm"
										disabled={accepting || (acceptedSuggestion !== null && acceptedSuggestion === suggestion)}
										onclick={() => accept(row.index)}>Use this</button
									>
								</td>
							{/if}
						</tr>
					{/each}
				</tbody>
			</table>
			{@render failure()}
			{#if canAct}
				<div class="mt-2">
					<button type="button" class="btn" onclick={() => onsearch?.()}>None of these, search</button>
				</div>
			{/if}
		</div>
	</div>
{:else if suggestion}
	<div class="identity-suggestion" data-testid="identity-suggestion">
		{#if suggestion.poster_url}
			<PosterImage url={suggestion.poster_url} alt={suggestion.title} class="identity-suggestion-poster shrink-0" />
		{/if}
		<div class="min-w-0 flex-1">
			<p class="identity-suggestion-heading">ARM found a match</p>
			<p class="identity-suggestion-match">
				{suggestion.year != null ? `${suggestion.title} (${suggestion.year})` : suggestion.title}
			</p>
			{#if tocCandidateCount > 1}
				<p class="identity-suggestion-source">
					One of {tocCandidateCount} releases that fit this disc's track layout. Use Search instead to pick another.
				</p>
			{/if}
			<p class="identity-suggestion-source">from {providerLabel(suggestion.provider)}</p>
			<MatchWhy {match} />
			{@render failure()}
			{#if canAct}
				<div class="mt-2 flex flex-wrap gap-2">
					<button
						type="button"
						class="btn btn-primary"
						disabled={accepting || (acceptedSuggestion !== null && acceptedSuggestion === suggestion)}
						onclick={() => accept()}>Use this title</button
					>
					<button type="button" class="btn" onclick={() => onsearch?.()}>Search instead</button>
				</div>
			{/if}
		</div>
	</div>
{/if}

<style>
	.identity-suggestion {
		display: flex;
		gap: 0.75rem;
		border-radius: var(--radius-md);
		border: 1px solid var(--color-accent-4);
		background: var(--color-surface-raised);
		padding: 0.625rem 0.75rem;
		font-size: 0.875rem;
	}
	/* :global: forwarded through PosterImage's class prop onto its own img */
	:global(.identity-suggestion-poster) {
		height: 5rem;
		width: 3.5rem;
		border-radius: var(--radius-sm);
		object-fit: cover;
	}
	.identity-suggestion-heading {
		font-weight: 600;
	}
	.identity-suggestion-match {
		color: var(--color-text);
	}
	.identity-suggestion-source {
		color: var(--color-text-muted);
		font-size: 0.8125rem;
	}
</style>
