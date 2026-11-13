<script lang="ts">
	import type { JobView } from '$lib/types/api.gen';
	import type { EpisodeStatus } from '$lib/episodes/status';
	import type { ReviewSections } from '$lib/stores/review-sections.svelte';
	import type { DiscReviewJobActions } from '$lib/stores/disc-review-job-actions.svelte';
	import { isAdmin } from '$lib/stores/auth';

	interface Props {
		/** The job the card shows; its actions flags decide the admin buttons. */
		job: JobView;
		/** Which sections of the card are open; the toggles open and close them. */
		sections: ReviewSections;
		/** The card's job actions: the busy flags and the delete confirmation. */
		actions: DiscReviewJobActions;
		/** Whether the disc is a video disc. */
		isVideo: boolean;
		/** Whether the disc is a music CD. */
		isMusic: boolean;
		/** Whether the disc already ripped and awaits a transcode session. */
		isPostRip: boolean;
		/** Whether the rip can be started from the card. */
		canStart: boolean;
		/** The episode matching state, or null when the card has no episodes. */
		episodeRow: EpisodeStatus | null;
		/** Whether this disc matched an earlier rip. */
		previouslyRipped: boolean;
		/** Whether the disc is an ISO rip. */
		fromIso: boolean;
		/** Called when Apply session is pressed. */
		onapplysession: () => void;
		/** Called when Cancel is pressed. */
		oncancel: () => void;
		/** Called when Start rip is pressed. */
		onstartrip: () => void;
	}

	let {
		job,
		sections,
		actions,
		isVideo,
		isMusic,
		isPostRip,
		canStart,
		episodeRow,
		previouslyRipped,
		fromIso,
		onapplysession,
		oncancel,
		onstartrip
	}: Props = $props();
</script>

<div class="flex flex-wrap items-center gap-1.5 disc-review-widget-actions">
	<button
		onclick={() => sections.toggle('info')}
		class="btn disc-review-widget-action-btn"
		aria-pressed={sections.isOpen('info')}
	>
		Info
	</button>
	{#if isVideo}
		<button
			onclick={() => sections.toggle('title')}
			class="btn disc-review-widget-action-btn"
			aria-pressed={sections.isOpen('title')}>Search</button
		>
	{/if}
	{#if episodeRow && (episodeRow.state !== 'matched' || sections.isOpen('episodes'))}
		<button
			onclick={() => sections.toggle('episodes')}
			class="btn disc-review-widget-action-btn"
			aria-pressed={sections.isOpen('episodes')}>Episodes</button
		>
	{/if}
	{#if isMusic}
		<button
			onclick={() => sections.toggle('music')}
			class="btn disc-review-widget-action-btn"
			aria-pressed={sections.isOpen('music')}>Search</button
		>
	{/if}
	{#if $isAdmin && job.actions.can_apply}
		<button
			onclick={onapplysession}
			class="btn {isPostRip ? 'disc-review-widget-success-btn' : 'disc-review-widget-action-btn'}"
			>{isPostRip ? 'Apply session & transcode' : 'Apply session'}</button
		>
	{/if}
	<a href="/jobs/{job.id}" class="btn disc-review-widget-action-btn"> View details </a>
	{#if $isAdmin && job.actions.can_abandon}
		<button
			onclick={oncancel}
			disabled={actions.cancelling}
			class="btn btn-danger ml-auto"
			title={fromIso ? 'Cancel the rip and remove the virtual drive' : undefined}
		>
			{actions.cancelling ? 'Cancelling...' : previouslyRipped ? 'Discard' : 'Cancel'}
		</button>
	{/if}
	{#if $isAdmin && job.actions.can_delete}
		<button onclick={() => (actions.confirmDelete = true)} disabled={actions.deleting} class="btn btn-danger ml-auto">
			{actions.deleting ? 'Deleting...' : 'Delete'}
		</button>
	{/if}
	{#if canStart && $isAdmin}
		<button
			onclick={onstartrip}
			disabled={actions.starting}
			class="btn disc-review-widget-success-btn"
			title={previouslyRipped ? 'Rip this disc again' : 'Save the metadata and start ripping this disc'}
		>
			{actions.starting ? 'Starting...' : previouslyRipped ? 'Rip again' : 'Start rip'}
		</button>
	{/if}
</div>

<style>
	.disc-review-widget-actions {
		border-top: 1px solid var(--color-border);
		background: color-mix(in srgb, var(--color-primary-tint-3) 50%, transparent);
		padding: 0.5rem 1rem;
	}
	/* the original action buttons were px-3 py-1.5 text-sm (0.75rem/0.375rem,
	   0.875rem) - between .btn's default and .btn-sm, so neither preset
	   alone matches; override both on the row's own .btn children. The
	   original border was a ring (box-shadow, no layout space), not .btn's
	   real 1px border, so border:0 here keeps the height exact. */
	.disc-review-widget-actions .btn {
		min-height: auto;
		padding: 0.375rem 0.75rem;
		font-size: 0.875rem;
		line-height: 1.25rem;
		border: 0;
	}
	/* the original inactive action button was a tinted fill (bg-primary/5,
	   ring-primary/25, text-gray-700), not .btn's bare-outline default
	   (transparent background, primary-text colour) */
	.disc-review-widget-action-btn {
		background: var(--color-primary-tint-1);
		box-shadow: 0 0 0 1px var(--color-border);
		color: var(--color-text-secondary);
	}
	.disc-review-widget-action-btn:hover {
		background: var(--color-primary-tint-2);
	}
	.disc-review-widget-action-btn[aria-pressed='true'] {
		background: var(--color-primary);
		color: var(--color-on-primary);
		box-shadow: none;
	}
	.disc-review-widget-success-btn {
		background: var(--color-success);
		color: var(--color-on-primary);
	}
	.disc-review-widget-success-btn:hover {
		background: var(--color-success);
		filter: brightness(0.9);
	}
	/* Cancel keeps .btn-danger's tone but the original border was a ring too */
	.disc-review-widget-actions .btn-danger {
		box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-danger) 30%, transparent);
	}
</style>
