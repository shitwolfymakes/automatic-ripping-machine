<script lang="ts">
	import { onMount } from 'svelte';
	// SidebarStats reads from the resources store.
	// BottomStatsBar owns the lifecycle (startResources/stopResources);
	// SidebarStats is a pure reader — calling startResources() here is safe
	// because start() resets any prior timer (idempotent), but to keep things
	// simple we only read $resources. If SidebarStats renders without
	// BottomStatsBar mounted, resources will show the initial empty snapshot
	// until BottomStatsBar mounts and starts the poll.
	import { resources } from '$lib/stores/resources.svelte';
	import { barColor, filesHref } from '$lib/dashboard/resource-bars';
	import { fade } from 'svelte/transition';
	import { fadeIn } from '$lib/ui/transitions';
	import { fetchSystemVersion } from '$lib/api/system';
	import { versionChipView, type VersionChipView } from '$lib/layout/version-chip';

	let chip = $state<VersionChipView | null>(null);
	let chipSettled = $state(false);

	// Read once on mount; a failed read leaves the chip out entirely.
	onMount(async () => {
		try {
			chip = versionChipView(await fetchSystemVersion());
		} catch {
			chip = null;
		} finally {
			chipSettled = true;
		}
	});

	// The panel is bottom-anchored, so anything arriving late at its foot (the
	// Storage rows with the first poll, the version chip) would shove CPU and
	// Mem upward. Draw it once the poll has landed and the version read is done.
	const ready = resources.initialized;
</script>

{#if $ready && chipSettled}
	<div data-sidebar-stats class="stats-bar-side" in:fade={fadeIn}>
		<div class="stack stack-sm">
			<!-- CPU -->
			<div>
				<div class="stats-bar-side-label flex items-center justify-between">
					<span>CPU</span>
					<span class="whitespace-nowrap">
						{$resources.cpu_percent.toFixed(0)}%
						{#if ($resources.cpu_temp ?? 0) > 0}
							<span class="stats-bar-side-temp">&nbsp;{($resources.cpu_temp ?? 0).toFixed(0)}&deg;C</span>
						{/if}
					</span>
				</div>
				<div class="progress progress-sm">
					<div class="progress-track">
						<div
							class="progress-fill"
							data-bar={barColor($resources.cpu_percent, 'cpu')}
							style:--progress="{Math.min(100, $resources.cpu_percent)}%"
						></div>
					</div>
				</div>
			</div>

			<!-- Memory -->
			<div>
				<div class="stats-bar-side-label flex items-center justify-between">
					<span>Mem</span>
					<span>{$resources.memory.used_gb} / {$resources.memory.total_gb} GB</span>
				</div>
				<div class="progress progress-sm">
					<div class="progress-track">
						<div
							class="progress-fill"
							data-bar={barColor($resources.memory.percent, 'mem')}
							style:--progress="{Math.min(100, $resources.memory.percent)}%"
						></div>
					</div>
				</div>
			</div>
		</div>

		<!-- Storage -->
		{#if $resources.storage.length}
			<div class="stack stack-sm stats-bar-side-storage">
				<p class="eyebrow sidebar-stats-heading">Storage</p>
				{#each $resources.storage as s (s.path)}
					<a href={filesHref(s.name)} class="stats-bar-side-row">
						<div class="stats-bar-side-label flex items-center justify-between">
							<span>{s.name}</span>
							<span>{s.free_gb} GB free</span>
						</div>
						<div class="progress progress-sm">
							<div class="progress-track">
								<div
									class="progress-fill"
									data-bar={barColor(s.percent, 'disk')}
									style:--progress="{Math.min(100, s.percent)}%"
								></div>
							</div>
						</div>
					</a>
				{/each}
			</div>
		{/if}

		{#if chip}
			<a
				class="version-chip"
				data-version-chip
				href={chip.href}
				target="_blank"
				rel="noopener noreferrer"
				aria-label={chip.label}
			>
				<span class="version-chip-id">
					<svg
						class="version-chip-mark"
						viewBox="0 0 16 16"
						width="14"
						height="14"
						fill="currentColor"
						aria-hidden="true"
					>
						<path
							d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 2-.27c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z"
						/>
					</svg>
					<span class="version-chip-text">{chip.version}</span>
				</span>
				{#if chip.state === 'update'}
					<span class="version-chip-update">Update available</span>
				{:else if chip.state === 'up-to-date'}
					<span class="version-chip-status"><span class="version-chip-dot" aria-hidden="true"></span>Up to date</span>
				{/if}
			</a>
		{/if}
	</div>
{/if}

<style>
	.version-chip {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		margin-top: 0.75rem;
		padding: 0.375rem 0.5rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		font-size: 0.6875rem;
		color: var(--color-text-muted);
		text-decoration: none;
		transition:
			border-color var(--motion-fast) var(--ease),
			color var(--motion-fast) var(--ease);
	}
	.version-chip:hover,
	.version-chip:focus-visible {
		border-color: var(--color-border-strong);
		color: var(--color-text);
	}
	.version-chip-id {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		min-width: 0;
	}
	.version-chip-mark {
		flex: none;
	}
	.version-chip-text {
		font-family: var(--font-mono, ui-monospace, monospace);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.version-chip-status {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		white-space: nowrap;
	}
	.version-chip-dot {
		width: 0.375rem;
		height: 0.375rem;
		border-radius: 50%;
		background: var(--color-success);
	}
	.version-chip-update {
		white-space: nowrap;
		color: var(--color-success);
	}
	.stats-bar-side {
		font-variant-numeric: tabular-nums;
		border-top: 1px solid var(--color-border);
		padding: 0.75rem;
	}
	.stats-bar-side-label {
		margin-bottom: 0.125rem;
		font-size: 0.6875rem;
		color: var(--color-text-muted);
	}
	.stats-bar-side-temp {
		color: var(--color-accent-1);
	}
	.stats-bar-side-storage {
		margin-top: 0.75rem;
	}
	/* The eyebrow block is 11px/0.12em; this panel heading has always been
	   10px/0.05em, and the extra height shifts the storage rows below it. */
	.sidebar-stats-heading {
		font-size: 10px;
		line-height: 1.5;
		letter-spacing: 0.05em;
		color: var(--color-text-faint);
	}
	.stats-bar-side-row {
		display: block;
		margin: 0 -0.25rem;
		padding: 0 0.25rem;
		border-radius: var(--radius-sm);
		transition: background-color var(--motion-fast) var(--ease);
	}
	.stats-bar-side-row:hover {
		background: var(--color-primary-tint-1);
	}
</style>
