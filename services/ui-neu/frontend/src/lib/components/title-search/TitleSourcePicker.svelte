<script lang="ts">
	// The title search's source picker, where a keyed source without a saved
	// key is disabled.
	import { sourceKeyed, type SearchSource, type SearchSourceOption } from '$lib/settings/search-providers';
	import type { KeyedSources } from '$lib/stores/config';

	interface Props {
		/** The search type's sources, in order. */
		options: SearchSourceOption[];
		/** The source the search uses. */
		source: SearchSource | undefined;
		/** Which keyed sources have a saved key. */
		keyed: KeyedSources;
		/** The operator picked a source. */
		onpick: (id: SearchSource) => void;
	}

	let { options, source, keyed, onpick }: Props = $props();
</script>

<select
	aria-label="Search with"
	value={source}
	onchange={(e) => onpick((e.target as HTMLSelectElement).value as SearchSource)}
	class="field-control title-search-source"
>
	{#each options as opt (opt.id)}
		{@const hasKey = sourceKeyed(opt.id, keyed)}
		<option value={opt.id} disabled={!hasKey}>{hasKey ? opt.label : `${opt.label} (needs API key)`}</option>
	{/each}
</select>

<style>
	/* source picker joined to the title box as one control */
	.title-search-source {
		width: auto;
		flex: none;
		border-top-right-radius: 0;
		border-bottom-right-radius: 0;
		background: var(--color-primary-tint-2);
	}
</style>
