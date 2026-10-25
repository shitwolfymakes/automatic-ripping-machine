<script lang="ts">
	import type { JobView, ResolveResponse } from '$lib/types/api.gen';
	import { acceptIdentitySuggestion } from '$lib/api/jobs';
	import { ApiError, NETWORK_ERROR_MESSAGE } from '$lib/api/client';
	import { identitySuggestionOf, providerLabel } from '$lib/utils/job-status';
	import PosterImage from './PosterImage.svelte';

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
	let accepting = $state(false);
	// The suggestion this banner accepted: its button stays disabled until the
	// parent's refresh drops the banner (a second accept would only get a 409).
	let acceptedSuggestion = $state.raw<typeof suggestion>(null);
	let errorMessage = $state<string | null>(null);

	async function accept() {
		accepting = true;
		errorMessage = null;
		try {
			const accepted = suggestion;
			const resp = await acceptIdentitySuggestion(job.id);
			acceptedSuggestion = accepted;
			onaccepted?.(resp);
		} catch (e) {
			errorMessage = e instanceof ApiError ? e.message : NETWORK_ERROR_MESSAGE;
		} finally {
			accepting = false;
		}
	}
</script>

{#if suggestion}
	<div class="identity-suggestion" data-testid="identity-suggestion">
		{#if suggestion.poster_url}
			<PosterImage url={suggestion.poster_url} alt={suggestion.title} class="identity-suggestion-poster shrink-0" />
		{/if}
		<div class="min-w-0 flex-1">
			<p class="identity-suggestion-heading">ARM found a match</p>
			<p class="identity-suggestion-match">
				{suggestion.year != null ? `${suggestion.title} (${suggestion.year})` : suggestion.title}
			</p>
			<p class="identity-suggestion-source">from {providerLabel(suggestion.provider)}</p>
			{#if errorMessage}
				<div class="alert alert-danger mt-2">{errorMessage}</div>
			{/if}
			{#if canAct}
				<div class="mt-2 flex flex-wrap gap-2">
					<button
						type="button"
						class="btn btn-primary"
						disabled={accepting || (acceptedSuggestion !== null && acceptedSuggestion === suggestion)}
						onclick={accept}>Use this title</button
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
