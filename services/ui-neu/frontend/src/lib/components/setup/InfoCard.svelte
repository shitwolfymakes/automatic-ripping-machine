<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		label: string;
		children: Snippet;
	}

	let { label, children }: Props = $props();
</script>

<div class="panel">
	<div class="eyebrow">{label}</div>
	<div class="info-card-body">
		{@render children()}
	</div>
</div>

<style>
	.info-card-body { margin-top: 0.25rem; }
</style>
