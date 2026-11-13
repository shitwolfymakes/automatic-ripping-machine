<script lang="ts">
	// One storage folder's card in System health, saying whether it is there
	// and writable, how much space it has free, and how to fix it when it
	// isn't.
	import type { PathStatus, StorageRoot } from '$lib/types/api.gen';
	import { freeLabel, pathState, storageHelp, storageLabel } from '$lib/dashboard/system-health';
	import Glyph from '$lib/components/Glyph.svelte';
	import CopyBlock from '$lib/components/CopyBlock.svelte';
	import HealthItem from './HealthItem.svelte';

	let { folder, storage }: { folder: PathStatus; storage: readonly StorageRoot[] | null } = $props();

	const st = $derived(pathState(folder));
</script>

<HealthItem
	testid="system-health-path"
	status={st}
	name={storageLabel(folder.name)}
	path={folder.path}
	description={storageHelp(folder.name)}
>
	{#snippet badge()}
		<span class="badge badge-sm {st === 'ok' ? 'badge-success' : 'badge-danger'}">
			{st === 'ok' ? 'OK' : 'Problem'}
		</span>
	{/snippet}
	{#snippet chips()}
		<span class="chip chip-sm {folder.exists ? 'chip-success' : 'chip-danger'}">
			<Glyph name={folder.exists ? 'check' : 'x'} class="h-3 w-3" />{folder.exists ? 'Exists' : 'Missing'}
		</span>
		<span class="chip chip-sm {folder.writable ? 'chip-success' : 'chip-danger'}">
			<Glyph name={folder.writable ? 'check' : 'x'} class="h-3 w-3" />{folder.writable ? 'Writable' : 'Not writable'}
		</span>
		<span class="chip chip-sm">{freeLabel(storage, folder.name)}</span>
	{/snippet}
	{#if st !== 'ok'}
		{#if folder.host_path}
			<p class="storage-path-item-hint">
				Host path <code class="mono">{folder.host_path}</code>. Run this on the server, then press Check again:
			</p>
			<CopyBlock text={`sudo chown -R ${folder.uid}:${folder.gid} ${folder.host_path}`} />
		{:else}
			<p class="storage-path-item-hint">Set ARM_HOST_*_PATH in .env so ARM can name the folder to fix.</p>
		{/if}
	{/if}
</HealthItem>

<style>
	/* matches System health's description lines */
	.storage-path-item-hint {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
</style>
