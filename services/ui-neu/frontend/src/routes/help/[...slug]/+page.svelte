<script lang="ts">
	import { tick } from 'svelte';
	import { page } from '$app/stores';
	import { fetchDocsNav, slugToId, type DocsNavSection } from '$lib/help/api';
	import HelpSearchBox from '$lib/components/help/HelpSearchBox.svelte';
	import HelpToc from '$lib/components/help/HelpToc.svelte';
	import HelpTopics from '$lib/components/help/HelpTopics.svelte';
	import { fragmentId, scrollToFragment } from '$lib/help/fragment';
	import { HelpDoc } from '$lib/stores/help-doc.svelte';
	import { HelpSearch } from '$lib/stores/help-search.svelte';

	const id = $derived(slugToId($page.params.slug));

	let nav = $state<DocsNavSection[]>([]);
	const helpDoc = new HelpDoc(() => id);
	const helpSearch = new HelpSearch();
	let topicsOpen = $state(false);

	fetchDocsNav()
		.then((n) => (nav = n))
		.catch(() => console.warn('help: nav.json unavailable'));

	$effect(() => {
		const current = id;
		helpSearch.clear();
		topicsOpen = false;
		helpDoc.load(current, async () => {
			// The fragment arrives after SvelteKit's own hash scroll ran.
			await tick();
			if (current !== id) return;
			scrollToFragment(fragmentId(location.hash));
		});
	});
</script>

<svelte:head>
	<title>ARM - {helpDoc.doc && helpDoc.status === 'ready' ? `${helpDoc.doc.title} - Help` : 'Help'}</title>
</svelte:head>

<div class="help-layout">
	<aside class="help-nav stack">
		<HelpSearchBox query={helpSearch.query} hits={helpSearch.hits} onsearch={helpSearch.run} />
		<HelpTopics {nav} activeId={id} bind:open={topicsOpen} />
	</aside>

	<div class="help-main">
		{#if helpDoc.status === 'loading'}
			<p class="help-status">Loading</p>
		{:else if helpDoc.status === 'ready' && helpDoc.doc}
			<!-- Trusted HTML: rendered at image build time by site/ from this
			     repo's own markdown (markdown-it with raw HTML disabled, no
			     scripts), served same-origin from /docs-data/. Never user input. -->
			<!-- eslint-disable-next-line svelte/no-at-html-tags -- trusted build-time HTML, see above -->
			<article class="docs-prose">{@html helpDoc.doc.html}</article>
			<p class="help-footer">
				<a class="btn btn-link" href={helpDoc.doc.editUrl} target="_blank" rel="noopener">Edit this page on GitHub</a>
			</p>
		{:else}
			<div class="alert alert-warning alert-lg">
				<p class="alert-title">{helpDoc.status === 'missing' ? 'Page not found' : 'Help is unavailable'}</p>
				<p class="alert-body">
					{helpDoc.status === 'missing'
						? 'There is no help page at this address.'
						: 'The help content could not be loaded.'}
					<a class="btn btn-link" href="/help">Back to Help</a>
				</p>
			</div>
		{/if}
	</div>

	{#if helpDoc.status === 'ready' && helpDoc.doc && helpDoc.doc.toc.length > 1}
		<HelpToc toc={helpDoc.doc.toc} />
	{/if}
</div>

<style>
	.help-layout {
		display: grid;
		grid-template-columns: 15rem minmax(0, 1fr) 13rem;
		gap: 2rem;
		align-items: start;
	}
	.help-nav {
		position: sticky;
		top: 0;
		/* the viewport less the shell around main's scroll area: the header
		   (h-14 unless a scheme says otherwise), main's lg:p-6 top padding, the
		   fixed stats bar when the layout shows one, and the same padding as a
		   gap above the bottom edge */
		max-height: calc(100dvh - var(--shell-header-height, 3.5rem) - var(--shell-footer-height, 0px) - 3rem);
		overflow-y: auto;
	}
	.help-status {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
	.help-main {
		min-width: 0;
	}
	.help-main .docs-prose {
		max-width: 75ch;
	}
	.help-footer {
		max-width: 75ch;
		margin-top: 2rem;
		padding-top: 1rem;
		border-top: 1px solid var(--color-border);
	}

	@media (max-width: 80rem) {
		.help-layout {
			grid-template-columns: 15rem minmax(0, 1fr);
		}
	}
	@media (max-width: 64rem) {
		.help-layout {
			grid-template-columns: minmax(0, 1fr);
			gap: 1rem;
		}
		.help-nav {
			position: static;
			max-height: none;
			overflow-y: visible;
		}
	}
</style>
