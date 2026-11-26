<script lang="ts">
	// The sidebar's version chip: the running version, linked to the release
	// when an update is out, else to the repo. Reads the version once on mount,
	// and reports when that read is over (answered, failed or timed out) so the
	// panel around it can draw without waiting longer than the timeout.
	import { onMount } from 'svelte';
	import { fetchSystemVersion } from '$lib/api/system';
	import {
		VERSION_CHIP_TIMEOUT_MS,
		versionChipView,
		withinTimeout,
		type VersionChipView
	} from '$lib/layout/version-chip';
	import BrandMark from '../shared/BrandMark.svelte';

	interface Props {
		/** Called once the version read is over. */
		onsettled?: () => void;
	}

	let { onsettled }: Props = $props();
	let chip = $state<VersionChipView | null>(null);

	onMount(async () => {
		chip = versionChipView(await withinTimeout(fetchSystemVersion, VERSION_CHIP_TIMEOUT_MS));
		onsettled?.();
	});
</script>

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
			<BrandMark name="github" class="version-chip-mark" />
			<span class="version-chip-text">{chip.version}</span>
		</span>
		{#if chip.state === 'update'}
			<span class="version-chip-update">Update available</span>
		{:else if chip.state === 'up-to-date'}
			<span class="version-chip-status"><span class="version-chip-dot" aria-hidden="true"></span>Up to date</span>
		{/if}
	</a>
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
</style>
