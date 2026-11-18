<script lang="ts">
	import CountdownTimer from '$lib/components/dashboard/CountdownTimer.svelte';

	interface Props {
		/** The status text shown beside the pulsing dot. */
		label: string;
		/** When the countdown started; the countdown shows only while this is set. */
		waitStartTime: string | null | undefined;
		/** How long the countdown runs, in seconds. */
		waitSeconds: number;
		/** Whether the countdown is frozen. */
		paused: boolean;
		/** The reason the ripper is holding the countdown, or null when it is not. */
		held: string | null;
		/** Called when the countdown's pause control is pressed. */
		onpause?: () => void;
		/** Called when the countdown's resume control is pressed. */
		onresume?: () => void;
	}

	let { label, waitStartTime, waitSeconds, paused, held, onpause, onresume }: Props = $props();
</script>

<div class="disc-review-widget-status-bar">
	<div class="flex items-center gap-2">
		<div class="disc-review-widget-status-dot"></div>
		<span class="disc-review-widget-status-label">
			{label}
		</span>
	</div>
	<!-- Timed review gate: cosmetic countdown to auto-start (the ripper owns the
			     real clock). Frozen by the global pause OR this disc's own pause. The
			     timer's pause/resume toggles THIS disc only (per-job manual_pause);
			     it's hidden while globally paused since one disc can't un-pause the
			     whole machine. -->
	{#if waitStartTime}
		<CountdownTimer startTime={waitStartTime} {waitSeconds} {paused} {held} inverted {onpause} {onresume} />
	{/if}
</div>

<style>
	.disc-review-widget-status-bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		background: color-mix(in srgb, var(--color-primary) 32%, var(--color-surface));
		border-bottom: 1px solid var(--color-border-strong);
		padding: 0.375rem 1rem;
	}
	.disc-review-widget-status-dot {
		height: 0.5rem;
		width: 0.5rem;
		flex-shrink: 0;
		border-radius: 9999px;
		background: var(--color-primary);
		animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
	}
	@keyframes pulse {
		50% {
			opacity: 0.5;
		}
	}
	.disc-review-widget-status-label {
		font-size: 1rem;
		line-height: 1.5rem;
		font-weight: 600;
		color: var(--color-primary-text);
	}
</style>
