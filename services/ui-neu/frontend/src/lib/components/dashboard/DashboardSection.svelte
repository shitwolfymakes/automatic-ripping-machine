<script lang="ts" generics="T">
	import type { Snippet } from 'svelte';
	import { fade } from 'svelte/transition';
	import { fadeIn, fadeOut } from '$lib/ui/transitions';
	import SectionFrame from '$lib/components/shared/SectionFrame.svelte';

	interface Props {
		items: T[];
		key: (item: T) => string;
		accent: string;
		label: string;
		emphasis?: boolean;
		listClass?: string;
		row: Snippet<[T]>;
	}

	let { items, key, accent, label, emphasis, listClass = 'space-y-2', row }: Props = $props();
</script>

{#if items.length > 0}
	<section in:fade={fadeIn} out:fade={fadeOut}>
		<SectionFrame variant="full" {accent} {emphasis} {label}>
			<div class={listClass}>
				{#each items as item (key(item))}
					<div in:fade|local={fadeIn} out:fade|local={fadeOut}>
						{@render row(item)}
					</div>
				{/each}
			</div>
		</SectionFrame>
	</section>
{/if}
