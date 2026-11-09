<script lang="ts">
	import NewFolderRow from '../NewFolderRow.svelte';

	let { onconfirm, oncancel }: { onconfirm: () => void; oncancel: () => void } = $props();
	let name = $state('');
</script>

<NewFolderRow bind:name {onconfirm} {oncancel} />
<span data-testid="bound-name">{name}</span>
