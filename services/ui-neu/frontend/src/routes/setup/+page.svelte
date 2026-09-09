<script lang="ts">
	import type { SetupStatus } from '$lib/api/setup';
	import SetupWizard from '$lib/components/setup/SetupWizard.svelte';

	let { data }: { data: { status: SetupStatus | null } } = $props();
</script>

<svelte:head>
	<title>ARM - Setup</title>
</svelte:head>

<div class="setup-page">
	{#if data.status}
		<SetupWizard status={data.status} />
	{:else}
		<div class="setup-page-error-wrap">
			<div class="alert alert-danger setup-page-error">
				Failed to load setup status
			</div>
		</div>
	{/if}
</div>

<style>
	.setup-page { min-height: 100vh; background: var(--color-page); }
	.setup-page-error-wrap { display: flex; min-height: 100vh; align-items: center; justify-content: center; }
	/* original had no text-size utility at all (p-6 text-red-700), so it
	   renders at the ambient body size (1rem/1.5rem), not .alert's own
	   text-sm (0.875rem/1.25rem) default */
	.setup-page-error { padding: 1.5rem; font-size: 1rem; line-height: 1.5rem; }
</style>
