<script lang="ts">
	import { errorMessage } from '$lib/utils/errors';
	import { onMount } from 'svelte';
	import { fetchSystemDiagnostics } from '$lib/api/system';
	import { fetchResources } from '$lib/api/resources';
	import type { SystemDiagnosticsResponse, StorageRoot } from '$lib/types/api.gen';
	import SystemHealthGrouped from './SystemHealthGrouped.svelte';
	import SystemHealthList from './SystemHealthList.svelte';

	// Settings > System and the setup walkthrough's System check share this.
	// `grouped`: Storage + Services panels with fix commands.
	// `scope="system"`: only what the System check step is about; drives and
	// the MakeMKV key are later steps. `autorun`: check on mount.
	let {
		autorun = false,
		grouped = false,
		scope = 'all',
		onresult
	}: {
		autorun?: boolean;
		grouped?: boolean;
		scope?: 'all' | 'system';
		onresult?: (r: SystemDiagnosticsResponse) => void;
	} = $props();

	let result = $state<SystemDiagnosticsResponse | null>(null);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let lastRun = $state<string | null>(null);

	let storage = $state<StorageRoot[] | null>(null);

	async function runChecks(): Promise<void> {
		loading = true;
		error = null;
		try {
			result = await fetchSystemDiagnostics();
			lastRun = new Date().toISOString();
			onresult?.(result);
		} catch (e) {
			error = errorMessage(e, 'Health checks failed');
		} finally {
			loading = false;
		}
		if (grouped) storage = await loadStorage();
	}

	/** The storage roots for the free-space chips, or null when the
	 * lookup fails. */
	async function loadStorage(): Promise<StorageRoot[] | null> {
		try {
			return (await fetchResources()).storage;
		} catch {
			return null;
		}
	}

	onMount(() => {
		if (autorun) void runChecks();
	});
</script>

{#if grouped}
	<SystemHealthGrouped {result} {error} {loading} {lastRun} {storage} {scope} onrun={runChecks} />
{:else}
	<SystemHealthList {result} {error} {loading} {lastRun} {scope} onrun={runChecks} />
{/if}
