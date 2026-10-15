<script lang="ts">
	import RecipeStrip from '$lib/components/sessions/RecipeStrip.svelte';
	import type { ConfigFieldMeta } from '$lib/types/api.gen';
	import { stripCells, type DiscKind } from '$lib/utils/identity-card';

	let { kind, values, fields }: { kind: DiscKind; values: Record<string, unknown>; fields: ConfigFieldMeta[] } =
		$props();

	const cells = $derived(stripCells(kind, values, fields));
</script>

<div role="group" aria-label="Identity summary">
	<RecipeStrip tone="info" {cells} />
</div>
