<script lang="ts">
	import type { Catalog, CatalogService } from '$lib/types/notifications';
	import ServiceGlyph from './ServiceGlyph.svelte';

	let {
		catalog,
		selectedId,
		onpick
	}: { catalog: Catalog; selectedId: string | null; onpick?: (id: string) => void } = $props();

	let open = $state(false);
	let search = $state('');
	let rootEl: HTMLDivElement | undefined = $state();

	const byId = $derived(new Map(catalog.services.map((s) => [s.id, s])));
	const selected = $derived(selectedId ? byId.get(selectedId) ?? null : null);

	const featured = $derived(
		catalog.featured.map((id) => byId.get(id)).filter((s): s is CatalogService => !!s)
	);
	const rest = $derived(
		catalog.services
			.filter((s) => !catalog.featured.includes(s.id))
			.sort((a, b) => a.name.localeCompare(b.name))
	);
	const q = $derived(search.trim().toLowerCase());
	const filtered = $derived(
		q ? catalog.services.filter((s) => s.name.toLowerCase().includes(q)) : null
	);

	function choose(id: string) {
		onpick?.(id);
		open = false;
		search = '';
	}

	$effect(() => {
		if (!open) return;
		function onDocClick(ev: MouseEvent) {
			if (rootEl && !rootEl.contains(ev.target as Node)) open = false;
		}
		document.addEventListener('mousedown', onDocClick, true);
		return () => document.removeEventListener('mousedown', onDocClick, true);
	});
</script>

<div class="service-dropdown" bind:this={rootEl}>
	<button
		type="button"
		onclick={() => (open = !open)}
		aria-expanded={open}
		class="service-dropdown-trigger"
	>
		{#if selected}
			<span class="cluster">
				<ServiceGlyph id={selected.id} name={selected.name} size={22} />
				<span class="service-dropdown-name">{selected.name}</span>
			</span>
		{:else}
			<span class="service-dropdown-placeholder">Select a service...</span>
		{/if}
		<svg class="service-dropdown-chevron" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
	</button>

	{#if open}
		<div class="service-dropdown-panel">
			<div class="service-dropdown-search">
				<!-- svelte-ignore a11y_autofocus -->
				<input type="search" placeholder="Search services" bind:value={search} autofocus class="field-control" />
			</div>
			<ul class="service-dropdown-list">
				{#if filtered}
					{#each filtered as svc (svc.id)}
						{@render option(svc)}
					{/each}
					{#if filtered.length === 0}
						<li class="service-dropdown-empty">No services match "{search}".</li>
					{/if}
				{:else}
					<li class="eyebrow service-dropdown-group">Featured</li>
					{#each featured as svc (svc.id)}{@render option(svc)}{/each}
					<li class="eyebrow service-dropdown-group service-dropdown-group-muted">All services</li>
					{#each rest as svc (svc.id)}{@render option(svc)}{/each}
				{/if}
			</ul>
		</div>
	{/if}
</div>

{#snippet option(svc: CatalogService)}
	<li>
		<button
			type="button"
			onclick={() => choose(svc.id)}
			class="flyout-item"
			aria-pressed={svc.id === selectedId}
		>
			<ServiceGlyph id={svc.id} name={svc.name} size={22} />
			<span class="service-dropdown-name">{svc.name}</span>
			<span class="mono service-dropdown-scheme">{svc.url_scheme}://</span>
		</button>
	</li>
{/snippet}

<style>
	/* The panel anchors under the trigger button (relative/absolute), unlike
	   the Flyout primitive's viewport-fixed positioning, so it stays a local
	   class rather than .flyout. */
	.service-dropdown { position: relative; }
	.service-dropdown-trigger {
		display: flex;
		width: 100%;
		align-items: center;
		justify-content: space-between;
		border: 1px solid var(--color-border-strong);
		border-radius: var(--radius-md);
		background: var(--color-primary-tint-1);
		padding: 0.625rem 0.75rem;
		text-align: left;
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text);
		cursor: pointer;
	}
	.service-dropdown-trigger:hover { border-color: var(--color-primary); }
	.service-dropdown-name { color: var(--color-text-secondary); }
	.service-dropdown-placeholder { color: var(--color-text-muted); }
	.service-dropdown-chevron { width: 1rem; height: 1rem; flex-shrink: 0; transition: transform var(--motion-fast) var(--ease); }
	.service-dropdown-trigger[aria-expanded="true"] .service-dropdown-chevron { transform: rotate(180deg); }
	.service-dropdown-panel {
		position: absolute;
		z-index: 20;
		margin-top: 0.25rem;
		width: 100%;
		overflow: hidden;
		border: 1px solid var(--color-border-strong);
		border-radius: var(--radius-md);
		background: var(--color-surface-raised);
		box-shadow: var(--shadow-2);
	}
	.service-dropdown-search { padding: 0.5rem; }
	.service-dropdown-list { max-height: 280px; overflow-y: auto; padding: 0.25rem 0; }
	.service-dropdown-empty { padding: 0.5rem 0.75rem; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	.service-dropdown-group { padding: 0.5rem 0.75rem 0.25rem; }
	.service-dropdown-group-muted { color: var(--color-text-muted); }
	.service-dropdown-scheme { margin-left: auto; font-size: 10.5px; color: var(--color-text-muted); }
	.service-dropdown-list .flyout-item[aria-pressed="true"] { background: var(--color-primary-tint-3); }
</style>
