<script lang="ts">
	import type { DispatchRow } from '$lib/types/notifications';

	let { rows }: { rows: DispatchRow[] } = $props();
</script>

{#if rows.length === 0}
	<p class="text-sm text-gray-500 dark:text-gray-400">No sends yet.</p>
{:else}
	<ul class="space-y-1">
		{#each rows as row (row.id)}
			<li class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
				<span
					class:text-status-success={row.status === 'success'}
					class:text-status-error={row.status === 'failed'}
					class:text-gray-400={row.status !== 'success' && row.status !== 'failed'}
				>
					{#if row.status === 'success'}
						<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>
					{:else if row.status === 'failed'}
						<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" /></svg>
					{:else}
						<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
					{/if}
				</span>
				<span class="font-medium">{row.event_key}</span>
				<span class="text-gray-400">{row.created_at ?? ''}</span>
				{#if row.last_error}
					<span class="text-status-error">| {row.last_error}</span>
				{/if}
			</li>
		{/each}
	</ul>
{/if}
