<script lang="ts">
	import type { DocsTocEntry } from '$lib/help/api';

	interface Props {
		toc: DocsTocEntry[];
	}

	let { toc }: Props = $props();
</script>

<nav class="help-toc" aria-label="On this page">
	<p class="eyebrow">On this page</p>
	{#each toc as entry (entry.id)}
		<a class="help-toc-link" data-depth={entry.depth} href={`#${entry.id}`}>{entry.text}</a>
	{/each}
</nav>

<style>
	.help-toc {
		position: sticky;
		top: 0;
		/* the viewport less the shell around main's scroll area: the header
		   (h-14 unless a scheme says otherwise), main's lg:p-6 top padding, the
		   fixed stats bar when the layout shows one, and the same padding as a
		   gap above the bottom edge */
		max-height: calc(100dvh - var(--shell-header-height, 3.5rem) - var(--shell-footer-height, 0px) - 3rem);
		overflow-y: auto;
	}
	.help-toc {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}
	.help-toc-link {
		padding: 0.125rem 0 0.125rem 0.75rem;
		border-left: 2px solid var(--color-border);
		font-size: 0.8125rem;
		color: var(--color-text-muted);
	}
	.help-toc-link[data-depth='3'] {
		padding-left: 1.5rem;
	}
	.help-toc-link:hover {
		color: var(--color-text);
	}

	@media (max-width: 80rem) {
		.help-toc {
			display: none;
		}
	}
</style>
