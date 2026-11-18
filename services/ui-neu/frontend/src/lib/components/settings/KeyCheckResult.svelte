<script lang="ts">
	// One API key check's result line: "Works", "Key rejected", "No key
	// set", the backend's note for a key it can't check, or "Couldn't
	// reach" the service, each with the check's detail where it has one.
	import type { KeyCheckResponse } from '$lib/types/api.gen';
	import { formatDateTime } from '$lib/utils/format';
	import Glyph from '$lib/components/shared/Glyph.svelte';

	interface Props {
		/** The check's result. */
		result: KeyCheckResponse;
		/** The service's name, for the "Couldn't reach" line. */
		service: string;
	}
	let { result, service }: Props = $props();
</script>

{#if result.status === 'ok'}
	<span class="flex items-center gap-1.5 key-check-result-success">
		<Glyph name="check-circle" class="shrink-0" />
		<strong>Works</strong>{#if result.detail}, {result.detail}{/if}{#if result.checked_at}<span class="mx-1"
				>&middot;</span
			>checked {formatDateTime(result.checked_at)}{/if}
	</span>
{:else if result.status === 'invalid'}
	<span class="flex items-center gap-1.5 key-check-result-danger">
		<Glyph name="x-circle" class="shrink-0" />
		<strong>Key rejected</strong>
	</span>
	{#if result.detail}<p class="mono key-check-result-detail">{result.detail}</p>{/if}
{:else if result.status === 'missing'}
	<span class="flex items-center gap-1.5 key-check-result-muted">
		<Glyph name="info" class="shrink-0" />
		No key set
	</span>
{:else if result.status === 'unknown'}
	<span class="flex items-center gap-1.5 key-check-result-warning">
		<Glyph name="question-circle" class="shrink-0" />
		{result.detail}
	</span>
{:else}
	<span class="flex items-center gap-1.5 key-check-result-warning">
		<Glyph name="warning" class="shrink-0" />
		<strong>Couldn't reach {service}</strong>
	</span>
	{#if result.detail}<p class="mono key-check-result-detail">{result.detail}</p>{/if}
{/if}

<style>
	.key-check-result-success {
		color: var(--color-success);
	}
	.key-check-result-danger {
		color: var(--color-danger);
	}
	.key-check-result-warning {
		color: var(--color-on-warning-soft);
	}
	.key-check-result-detail {
		margin-top: 0.25rem;
		font-size: 0.75rem;
		color: var(--color-text-muted);
		overflow-wrap: anywhere;
	}
	.key-check-result-muted {
		color: var(--color-text-muted);
	}
</style>
