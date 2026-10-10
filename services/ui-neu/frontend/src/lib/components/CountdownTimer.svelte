<script lang="ts">
	import { onMount } from 'svelte';

	interface Props {
		startTime: string;
		waitSeconds: number;
		paused?: boolean;
		/** Render with white text/track for use on colored backgrounds */
		inverted?: boolean;
		onpause?: () => void;
		onresume?: () => void;
	}

	let { startTime, waitSeconds, paused = false, inverted = false, onpause, onresume }: Props = $props();

	let now = $state(Date.now());
	let deadline = $derived(new Date(startTime).getTime() + waitSeconds * 1000);
	let remaining = $derived(Math.max(0, Math.ceil((deadline - now) / 1000)));
	let minutes = $derived(Math.floor(remaining / 60));
	let seconds = $derived(remaining % 60);
	let progress = $derived(
		waitSeconds > 0 ? Math.min(1, Math.max(0, 1 - remaining / waitSeconds)) : 1
	);
	let expired = $derived(remaining <= 0);

	function handleClick() {
		if (paused) {
			onresume?.();
		} else {
			onpause?.();
		}
	}

	onMount(() => {
		const id = setInterval(() => {
			if (!paused) {
				now = Date.now();
			}
		}, 1000);
		return () => clearInterval(id);
	});
</script>

<div class="countdown-timer" data-inverted={inverted}>
	<button
		type="button"
		onclick={handleClick}
		class="countdown-timer-btn"
		title={paused ? 'Resume timer' : 'Pause timer'}
	>
		{#if paused}
			<!-- Play icon -->
			<svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor">
				<path d="M8 5v14l11-7z" />
			</svg>
		{:else}
			<!-- Pause icon -->
			<svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor">
				<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
			</svg>
		{/if}
	</button>

	{#if paused}
		<span class="countdown-timer-label">Paused</span>
	{:else if expired}
		<span class="countdown-timer-label">Auto-proceeding...</span>
	{:else}
		<span class="countdown-timer-label countdown-timer-value">
			{minutes}m {String(seconds).padStart(2, '0')}s
		</span>
		<div class="progress countdown-timer-track">
			<div class="progress-track">
				<div data-progress-fill class="progress-fill" style:--progress="{progress * 100}%"></div>
			</div>
		</div>
	{/if}
</div>

<style>
	.countdown-timer { display: flex; align-items: center; gap: 0.5rem; }
	.countdown-timer-btn {
		display: flex; align-items: center; justify-content: center;
		width: 1.25rem; height: 1.25rem; flex-shrink: 0; border-radius: 9999px; border: 0; background: none;
		color: var(--color-primary-text); cursor: pointer;
		transition: background-color var(--motion-fast) var(--ease), color var(--motion-fast) var(--ease);
	}
	.countdown-timer-btn:hover { background: var(--color-primary-tint-3); }
	.countdown-timer-label { font-size: 0.875rem; font-weight: 500; color: var(--color-primary-text); }
	.countdown-timer-value { font-variant-numeric: tabular-nums; }
	.countdown-timer-track { width: 5rem; }
	.countdown-timer-track .progress-track { height: 0.375rem; }
	/* ticks once per second; the block's default 250ms fill transition is too
	   quick for that cadence, so this keeps the original 1s linear pace. */
	.countdown-timer-track .progress-fill { transition-duration: 1000ms; }
	/* inverted: rendered on a colored (accent) background, e.g. the review-gate
	   panel, so text/track/fill switch to on-primary tones instead of the
	   primary-text/primary-tint roles meant for a plain surface. */
	.countdown-timer[data-inverted="true"] .countdown-timer-btn { color: color-mix(in srgb, var(--color-on-primary) 90%, transparent); }
	/* inverted sits on a coloured fill, so the hover scrim is the on-primary
	   white rather than a surface token. */
	.countdown-timer[data-inverted="true"] .countdown-timer-btn:hover { background: color-mix(in srgb, var(--color-on-primary) 20%, transparent); }
	.countdown-timer[data-inverted="true"] .countdown-timer-label { color: color-mix(in srgb, var(--color-on-primary) 90%, transparent); }
	.countdown-timer[data-inverted="true"] .countdown-timer-track .progress-track { background: color-mix(in srgb, var(--color-on-primary) 25%, transparent); }
	.countdown-timer[data-inverted="true"] .countdown-timer-track .progress-fill { background: color-mix(in srgb, var(--color-on-primary) 80%, transparent); }
</style>
