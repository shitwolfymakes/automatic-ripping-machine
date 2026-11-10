<script lang="ts">
	import type { DriveView } from '$lib/types/api.gen';
	import Glyph from '$lib/components/Glyph.svelte';
	import { driveTitle } from '$lib/utils/drives';

	// The "Insert a disc to try it" card: what the watched drive is doing.
	let { target, ripStarted }: { target: DriveView | null; ripStarted: boolean } = $props();
</script>

<section class="panel first-disc-card" data-testid="finish-disc">
	<span class="first-disc-card-icon" aria-hidden="true"><Glyph name="disc-3" class="h-7 w-7" /></span>
	<div class="stack stack-sm">
		<h2 class="first-disc-card-title">Insert a disc to try it</h2>
		<p class="first-disc-card-status" role="status" aria-live="polite">
			{#if !target}
				<a href="/setup/drives">Enroll a drive to try it.</a>
			{:else if ripStarted}
				<Glyph name="check-circle" /> Ripping started in {driveTitle(target)}
			{:else if target.media_status === 'loaded'}
				<Glyph name="check-circle" /> Disc detected in {driveTitle(target)}
			{:else}
				<span class="first-disc-card-dot" aria-hidden="true"></span> Waiting for a disc in {driveTitle(target)}...
			{/if}
		</p>
		<p class="first-disc-card-help">
			Put any DVD, Blu-ray or CD in the drive. You can leave this page; the rip carries on.
		</p>
	</div>
</section>

<style>
	.first-disc-card {
		display: flex;
		align-items: flex-start;
		gap: 1rem;
		border: 1px solid var(--color-primary);
		padding: 1.25rem;
	}
	.first-disc-card-icon {
		flex: none;
		display: grid;
		place-items: center;
		width: 3.25rem;
		height: 3.25rem;
		border-radius: var(--radius-lg);
		background: var(--color-primary-tint-2);
		color: var(--color-primary-text);
	}
	.first-disc-card-title {
		font-size: 1.0625rem;
		font-weight: 600;
	}
	.first-disc-card-status {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-weight: 600;
	}
	.first-disc-card-dot {
		width: 0.5rem;
		height: 0.5rem;
		border-radius: 999px;
		background: var(--color-primary);
		animation: first-disc-card-pulse 1.6s ease-in-out infinite;
	}
	@keyframes first-disc-card-pulse {
		50% {
			opacity: 0.35;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.first-disc-card-dot {
			animation: none;
		}
	}
	.first-disc-card-help {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
</style>
