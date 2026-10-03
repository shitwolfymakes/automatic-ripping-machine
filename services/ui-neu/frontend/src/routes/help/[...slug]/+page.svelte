<script lang="ts">
	import { tick } from 'svelte';
	import { page } from '$app/stores';
	import type MiniSearch from 'minisearch';
	import {
		fetchDocsNav,
		fetchDocsPage,
		loadDocsSearch,
		searchDocs,
		slugToId,
		DocsNotFoundError,
		type DocsNavSection,
		type DocsPage,
		type DocsSearchHit
	} from '$lib/docs/api';

	const id = $derived(slugToId($page.params.slug));

	let nav = $state<DocsNavSection[]>([]);
	let doc = $state<DocsPage | null>(null);
	let status = $state<'loading' | 'ready' | 'missing' | 'error'>('loading');
	let query = $state('');
	let hits = $state<DocsSearchHit[]>([]);
	let topicsOpen = $state(false);
	let search: MiniSearch | null = null;

	fetchDocsNav()
		.then((n) => (nav = n))
		.catch(() => console.warn('help: nav.json unavailable'));

	$effect(() => {
		const current = id;
		status = 'loading';
		query = '';
		hits = [];
		topicsOpen = false;
		fetchDocsPage(current)
			.then(async (p) => {
				if (current !== id) return;
				doc = p;
				status = 'ready';
				// The fragment arrives after SvelteKit's own hash scroll ran.
				await tick();
				if (current !== id) return;
				const raw = location.hash.slice(1);
				let hash = raw;
				try {
					hash = decodeURIComponent(raw);
				} catch {
					// Malformed percent-encoding: fall back to the raw hash rather
					// than failing the whole page load.
				}
				if (hash) document.getElementById(hash)?.scrollIntoView();
				// The app scrolls inside <main>, not the window, so a plain
				// navigation (no hash) needs its own scroll-to-top.
				else document.querySelector('main')?.scrollTo(0, 0);
			})
			.catch((e) => {
				if (current !== id) return;
				doc = null;
				status = e instanceof DocsNotFoundError ? 'missing' : 'error';
			});
	});

	// Takes the value from the event rather than bind:value, so the query is
	// never read before the binding has updated it.
	async function onSearch(value: string) {
		query = value;
		if (!query.trim()) {
			hits = [];
			return;
		}
		try {
			search ??= await loadDocsSearch();
			hits = searchDocs(search, query);
		} catch {
			console.warn('help: search.json unavailable');
			hits = [];
		}
	}
</script>

<svelte:head>
	<title>ARM - {doc && status === 'ready' ? `${doc.title} - Help` : 'Help'}</title>
</svelte:head>

<div class="help-layout">
	<aside class="help-nav stack">
		<input
			type="search"
			class="field-control"
			placeholder="Search help"
			aria-label="Search help"
			autocomplete="off"
			value={query}
			oninput={(e) => onSearch(e.currentTarget.value)}
		/>
		{#if query.trim()}
			<div class="panel panel-compact help-results">
				{#each hits as hit (hit.id)}
					<a class="nav-item" href={hit.href}>{hit.title}</a>
				{:else}
					<p class="help-empty">No matches</p>
				{/each}
			</div>
		{/if}
		<button
			type="button"
			class="btn btn-sm help-topics-toggle"
			aria-expanded={topicsOpen}
			aria-controls="help-topics"
			onclick={() => (topicsOpen = !topicsOpen)}
		>
			Topics
		</button>
		<nav id="help-topics" class="nav help-topics" data-open={topicsOpen} aria-label="Help topics">
			{#each nav as section (section.id)}
				<p class="eyebrow help-section">{section.label}</p>
				{#each section.groups as group, gi (gi)}
					{#if group.label}<p class="help-group">{group.label}</p>{/if}
					{#each group.items as item, ii (ii)}
						<a
							class="nav-item"
							href={item.href}
							data-active={item.pageId === id ? 'true' : undefined}
							aria-current={item.pageId === id ? 'page' : undefined}
							target={item.external ? '_blank' : undefined}
							rel={item.external ? 'noopener' : undefined}>{item.label}</a
						>
					{/each}
				{/each}
			{/each}
		</nav>
	</aside>

	<div class="help-main">
		{#if status === 'loading'}
			<p class="help-status">Loading</p>
		{:else if status === 'ready' && doc}
			<!-- Trusted HTML: rendered at image build time by site/ from this
			     repo's own markdown (markdown-it with raw HTML disabled, no
			     scripts), served same-origin from /docs-data/. Never user input. -->
			<!-- eslint-disable-next-line svelte/no-at-html-tags -- trusted build-time HTML, see above -->
			<article class="docs-prose">{@html doc.html}</article>
			<p class="help-footer">
				<a class="btn btn-link" href={doc.editUrl} target="_blank" rel="noopener">Edit this page on GitHub</a>
			</p>
		{:else}
			<div class="alert alert-warning alert-lg">
				<p class="alert-title">{status === 'missing' ? 'Page not found' : 'Help is unavailable'}</p>
				<p class="alert-body">
					{status === 'missing' ? 'There is no help page at this address.' : 'The help content could not be loaded.'}
					<a class="btn btn-link" href="/help">Back to Help</a>
				</p>
			</div>
		{/if}
	</div>

	{#if status === 'ready' && doc && doc.toc.length > 1}
		<nav class="help-toc" aria-label="On this page">
			<p class="eyebrow">On this page</p>
			{#each doc.toc as entry (entry.id)}
				<a class="help-toc-link" data-depth={entry.depth} href={`#${entry.id}`}>{entry.text}</a>
			{/each}
		</nav>
	{/if}
</div>

<style>
	.help-layout {
		display: grid;
		grid-template-columns: 15rem minmax(0, 1fr) 13rem;
		gap: 2rem;
		align-items: start;
	}
	.help-nav,
	.help-toc {
		position: sticky;
		top: 0;
		max-height: calc(100dvh - 6rem);
		overflow-y: auto;
	}
	.help-topics {
		padding: 0;
	}
	.help-topics-toggle {
		display: none;
	}
	.help-section {
		margin-top: 0.75rem;
		padding: 0 0.75rem;
	}
	.help-group {
		margin: 0.5rem 0 0;
		padding: 0 0.75rem;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--color-text-muted);
	}
	.help-empty,
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
		.help-layout {
			grid-template-columns: 15rem minmax(0, 1fr);
		}
		.help-toc {
			display: none;
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
		.help-topics-toggle {
			display: inline-flex;
		}
		.help-topics:not([data-open='true']) {
			display: none;
		}
	}
</style>
