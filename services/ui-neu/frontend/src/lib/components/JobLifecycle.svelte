<script lang="ts">
	import { deriveLifecycle, lifecycleColorVar } from '$lib/utils/job-lifecycle';
	import { Pause } from 'lucide-svelte';

	interface Props {
		status: string | null | undefined;
		sourceType: string | null | undefined;
		size?: 'sm' | 'md';
		partial?: boolean;
	}

	let { status, sourceType, size = 'md', partial = false }: Props = $props();

	let nodes = $derived(deriveLifecycle(status, sourceType));
</script>

{#if size === 'sm'}
	<!-- Compact horizontal segments for the dashboard JobCard.
	     Each segment is a colored bar; the active one pulses; failure
	     segments use the error theme token. No labels rendered. -->
	<div
		class="inline-flex items-center gap-0.5"
		role="img"
		aria-label="Job lifecycle"
		title={nodes.map((n) => `${n.label}: ${n.state}`).join(' | ')}
	>
		{#each nodes as node (node.id)}
			<span
				class="job-lifecycle-seg"
				data-state={node.id === 'complete' && node.state === 'completed' && partial ? 'paused' : node.state}
				style:--node-color={node.id === 'complete' && node.state === 'completed' && partial ? 'var(--color-status-waiting)' : lifecycleColorVar(node.state)}
			>
				{#if node.state === 'paused'}
					<Pause class="job-lifecycle-pause-sm" />
				{/if}
			</span>
		{/each}
	</div>
{:else}
	<!-- Detail-page sized: each stage is a block with the label above a
	     small colored bar. Stages laid out side-by-side. -->
	<ol
		class="job-lifecycle-track"
		style:--cols={nodes.length}
		role="list"
		aria-label="Job lifecycle"
	>
		{#each nodes as node (node.id)}
			<li class="flex flex-col gap-1.5" title={`${node.label}: ${node.state}`}>
				<div class="job-lifecycle-label" data-state={node.state}>
					{#if node.state === 'paused'}
						<Pause class="h-3 w-3" />
					{/if}
					<span class="truncate">{node.label}</span>
				</div>
				<span
					class="job-lifecycle-bar"
					data-state={node.id === 'complete' && node.state === 'completed' && partial ? 'paused' : node.state}
					style:--node-color={node.id === 'complete' && node.state === 'completed' && partial ? 'var(--color-status-waiting)' : lifecycleColorVar(node.state)}
					aria-hidden="true"
				></span>
			</li>
		{/each}
	</ol>
{/if}

<style>
	@keyframes lifecyclePulse {
		0%, 100% {
			filter: brightness(1);
		}
		50% {
			filter: brightness(1.3);
		}
	}

	.job-lifecycle-seg { position: relative; height: 0.375rem; width: 1.5rem; border-radius: var(--radius-sm); background: var(--node-color); opacity: 1; }
	.job-lifecycle-seg[data-state="pending"] { opacity: 0.35; }
	.job-lifecycle-seg[data-state="active"] { animation: lifecyclePulse 1.4s ease-in-out infinite; }
	/* :global: forwarded through lucide Pause's class prop onto its own svg */
	:global(.job-lifecycle-pause-sm) { position: absolute; top: -0.25rem; left: 50%; height: 0.625rem; width: 0.625rem; transform: translateX(-50%); color: var(--color-status-waiting); }

	.job-lifecycle-track { display: grid; grid-template-columns: repeat(var(--cols), minmax(0, 1fr)); width: 100%; gap: 0.5rem; font-size: 0.75rem; line-height: 1rem; }
	.job-lifecycle-label { display: flex; align-items: center; gap: 0.25rem; font-size: 11px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-text); opacity: 1; }
	.job-lifecycle-label[data-state="pending"] { color: var(--color-status-pending, var(--color-text-faint)); opacity: 0.55; }
	.job-lifecycle-label[data-state="failed"] { color: var(--color-status-error); opacity: 1; }
	.job-lifecycle-bar { display: block; height: 0.5rem; width: 100%; border-radius: var(--radius-sm); background: var(--node-color); opacity: 1; }
	.job-lifecycle-bar[data-state="pending"] { opacity: 0.35; }
	.job-lifecycle-bar[data-state="active"] { animation: lifecyclePulse 1.4s ease-in-out infinite; }
</style>
