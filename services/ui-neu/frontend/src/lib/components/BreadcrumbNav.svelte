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

<nav class="flex items-center gap-1 text-sm text-gray-600 dark:text-gray-400">
	{#each segments as segment, i}
		{#if i > 0}
			<svg class="h-4 w-4 shrink-0 text-gray-400 dark:text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
			</svg>
		{/if}
		{#if i === segments.length - 1}
			<span class="font-medium text-gray-900 dark:text-white">{segment.label}</span>
		{:else}
			<button
				type="button"
				onclick={() => onnavigate(segment.root, segment.subpath)}
				class="transition-colors hover:text-primary dark:hover:text-primary-text-dark"
			>
				{segment.label}
			</button>
		{/if}
	{/each}
</nav>
