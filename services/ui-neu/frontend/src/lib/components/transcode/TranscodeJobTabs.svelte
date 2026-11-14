<script lang="ts">
	interface Props {
		active: string;
		onselect: (tab: string) => void;
	}

	let { active, onselect }: Props = $props();

	const tabs = ['all', 'queued', 'in_progress', 'done', 'failed'];
	// Pretty tab labels — `capitalize` alone leaves "in_progress" → "In_progress".
	const TAB_LABELS: Record<string, string> = {
		all: 'All',
		queued: 'Queued',
		in_progress: 'In Progress',
		done: 'Done',
		failed: 'Failed'
	};
</script>

<div class="tabs transcoder-page-tabs">
	{#each tabs as tab (tab)}
		<button onclick={() => onselect(tab)} data-selected={active === tab} class="tabs-tab transcoder-page-tab">
			{TAB_LABELS[tab]}
		</button>
	{/each}
</div>

<style>
	/* the tab strip has no overflow-x-auto and its buttons have no
	   whitespace-nowrap - at narrow widths the row itself shrinks and
	   "In Progress" wraps to two lines, rather than the strip scrolling
	   horizontally with single-line tabs */
	/* the tab strip gap is 0.25rem, not .tabs' own 1rem
	   default (tuned for the wider Settings tab strip); no overflow-x-auto
	   either, so the row shrinks and wraps rather than scrolling. Both axes
	   are reset: .tabs hides overflow-y, and a hidden y axis would turn a
	   visible x axis back into auto. */
	.transcoder-page-tabs {
		gap: 0.25rem;
		overflow: visible;
	}
	/* the buttons are px-4 py-2 (1rem/0.5rem), not .tabs-tab's own
	   0.25rem/0.625rem default, and have no whitespace-nowrap */
	.transcoder-page-tab {
		padding: 0.5rem 1rem;
		white-space: normal;
		flex-shrink: 1;
		min-width: 0;
		text-align: center;
	}
</style>
