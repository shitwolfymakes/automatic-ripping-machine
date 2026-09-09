<script lang="ts">
	import type { FileRoot } from '$lib/api/files';
	interface Props {
		root: string;
		subpath: string;
		roots: FileRoot[];
		onnavigate: (root: string, subpath: string) => void;
	}

	let { root, subpath, roots, onnavigate }: Props = $props();

	let segments = $derived.by(() => {
		const rootObj = roots.find((r) => r.key === root);
		const rootLabel = rootObj?.label ?? root;

		// First crumb: the root itself (subpath='')
		const result: { label: string; root: string; subpath: string }[] = [
			{ label: rootLabel, root, subpath: '' }
		];

		if (subpath) {
			const parts = subpath.split('/').filter(Boolean);
			let accumulated = '';
			for (const part of parts) {
				accumulated = accumulated ? `${accumulated}/${part}` : part;
				result.push({ label: part, root, subpath: accumulated });
			}
		}

		return result;
	});
</script>

<nav class="breadcrumb flex items-center gap-1">
	{#each segments as segment, i}
		{#if i > 0}
			<svg class="breadcrumb-sep shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
			</svg>
		{/if}
		{#if i === segments.length - 1}
			<span class="breadcrumb-current">{segment.label}</span>
		{:else}
			<button
				type="button"
				onclick={() => onnavigate(segment.root, segment.subpath)}
				class="breadcrumb-crumb"
			>
				{segment.label}
			</button>
		{/if}
	{/each}
</nav>

<style>
	.breadcrumb {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
	.breadcrumb-sep {
		width: 1rem;
		height: 1rem;
		color: var(--color-text-faint);
	}
	.breadcrumb-current {
		font-weight: 500;
		color: var(--color-text);
	}
	.breadcrumb-crumb {
		transition: color var(--motion-fast) var(--ease);
	}
	.breadcrumb-crumb:hover {
		color: var(--color-primary-text);
	}
</style>
