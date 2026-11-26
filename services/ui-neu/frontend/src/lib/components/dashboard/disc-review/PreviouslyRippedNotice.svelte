<script lang="ts">
	import type { PreviousRipView } from '$lib/types/api.gen';
	import { formatDateTime } from '$lib/utils/format';

	interface Props {
		/** The earlier rip, or null when the detail has none. */
		previous: PreviousRipView | null;
		/** The card's first detail load is still running. */
		loading: boolean;
	}

	let { previous, loading }: Props = $props();
</script>

<div class="disc-review-widget-previous" data-testid="previously-ripped">
	{#if previous}
		<p>
			ARM already ripped this disc as
			<a href="/jobs/{previous.job_id}" class="disc-review-widget-previous-link"
				>{previous.title?.trim() || 'an untitled disc'}</a
			>{#if previous.ripped_at}&nbsp;on {formatDateTime(previous.ripped_at)}{/if}{previous.status === 'ripped_partial'
				? ', partially.'
				: '.'}
		</p>
		<p class="disc-review-widget-previous-sub">
			{previous.outputs_present === true
				? 'Its files are still in the library.'
				: previous.outputs_present === false
					? 'Some of its files are no longer in the library.'
					: 'It has no transcoded files.'}
		</p>
	{:else if !loading}
		<p>ARM ripped this disc before, but that job has since been deleted.</p>
	{/if}
</div>

<style>
	/* mixed from text + surface rather than --color-surface-raised, which
	   most schemes leave unset */
	.disc-review-widget-previous {
		margin: 0 1rem 0.75rem;
		border-radius: var(--radius-md);
		border: 1px solid var(--color-border);
		background: color-mix(in srgb, var(--color-text) 4%, var(--color-surface));
		padding: 0.625rem 0.75rem;
		font-size: 0.875rem;
	}
	.disc-review-widget-previous-link {
		font-weight: 600;
		color: var(--color-primary);
		text-decoration: underline;
	}
	.disc-review-widget-previous-sub {
		margin-top: 0.25rem;
		color: var(--color-text-muted);
	}
</style>
