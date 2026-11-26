<script lang="ts">
	// The five-stage rail and its readout, drawn from jobProgress. Watching the
	// job here means any surface that mounts a StageRail gets live numbers.
	import type { JobView } from '$lib/types/api.gen';
	import { dashboard } from '$lib/stores/dashboard';
	import { jobLive } from '$lib/stores/job-live.svelte';
	import {
		isCountingDown,
		jobProgress,
		type ProgressContext,
		type ProgressJob,
		type RailStage
	} from '$lib/jobs/progress';

	interface Props {
		job: ProgressJob & Pick<JobView, 'id'>;
		size?: 'sm' | 'md';
	}

	let { job, size = 'sm' }: Props = $props();

	let now = $state(Date.now());

	// The dashboard store may not have loaded; fall back to the defaults.
	let reviewWaitSeconds = $derived($dashboard?.review_wait_seconds ?? 60);
	let rippingPaused = $derived($dashboard?.ripping_enabled === false);
	let ctx: ProgressContext = $derived({ now, reviewWaitSeconds, rippingPaused });

	// Re-watch exactly when the id or status changes, not on other field updates.
	// The deriveds only notify on a changed value, so a fresh job object with the
	// same id and status does not re-run the effect.
	let watchId = $derived(job.id);
	let watchStatus = $derived(job.status);
	$effect(() => {
		const id = watchId;
		const status = watchStatus;
		return jobLive.watch({ id, status });
	});

	// A boolean, so the tick below restarts only when the countdown starts or stops.
	let counting = $derived(isCountingDown(job, { now: 0, reviewWaitSeconds, rippingPaused }));

	$effect(() => {
		if (!counting) return;
		now = Date.now();
		const timer = setInterval(() => (now = Date.now()), 1000);
		return () => clearInterval(timer);
	});

	let view = $derived(jobProgress(job, jobLive.get(job.id), ctx));

	/** A known percent is clamped so a sliver stays visible; unknown fills the bar (and pulses). */
	function fillWidth(pct: number | null): string {
		return pct == null ? '100%' : `${Math.max(2, Math.min(100, pct))}%`;
	}

	const HUE: Record<RailStage, string> = {
		waiting: 'var(--color-status-waiting)',
		identifying: 'var(--color-status-scanning)',
		ripping: 'var(--color-status-ripping)',
		transcoding: 'var(--color-status-transcoding)',
		complete: 'var(--color-status-success)'
	};
</script>

<div class="stage-rail" data-size={size}>
	<ol class="stage-rail-track" aria-label="Job stages">
		{#each view.segments as seg (seg.stage)}
			<li class="stage-rail-step" data-state={seg.state} style:--hue={HUE[seg.stage]}>
				<span class="stage-rail-bar" aria-hidden="true">
					{#if seg.state === 'active'}
						<span class="stage-rail-fill" data-known={seg.pct != null} style:--fill-width={fillWidth(seg.pct)}></span>
					{/if}
				</span>
				<span class="stage-rail-label">{seg.label}<span class="sr-only">: {seg.state}</span></span>
			</li>
		{/each}
	</ol>
	<p class="stage-rail-readout" data-tone={view.readout.tone}>
		<span class="min-w-0 truncate">
			<strong class="stage-rail-readout-label">{view.readout.label}</strong>
			{#if view.readout.detail}<span class="stage-rail-readout-detail">{view.readout.detail}</span>{/if}
		</span>
		{#if view.readout.figure}<span class="stage-rail-figure">{view.readout.figure}</span>{/if}
	</p>
</div>

<style>
	@keyframes stage-rail-breathe {
		0%,
		100% {
			opacity: 0.35;
		}
		50% {
			opacity: 0.85;
		}
	}
	/* Text colours: each mix reaches 4.5:1 on --color-surface in both schemes
	   (the raw status hues and --color-text-muted fall short in light mode).
	   The bars keep the raw status colours. */
	.stage-rail {
		--rail-text-pending: color-mix(in srgb, var(--color-text-muted) 90%, var(--color-text));
		--rail-text-quiet: color-mix(in srgb, var(--color-text-muted) 80%, var(--color-text));
		--rail-text-waiting: color-mix(in srgb, var(--color-status-waiting) 50%, var(--color-text));
		--rail-text-success: color-mix(in srgb, var(--color-status-success) 55%, var(--color-text));
		--rail-text-error: color-mix(in srgb, var(--color-status-error) 75%, var(--color-text));
	}
	.stage-rail-track {
		display: grid;
		grid-template-columns: repeat(5, minmax(0, 1fr));
		gap: 0.25rem;
	}
	.stage-rail-step {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.375rem;
	}
	.stage-rail-bar {
		position: relative;
		width: 100%;
		height: 0.375rem;
		overflow: hidden;
		border-radius: 9999px;
		background: color-mix(in srgb, var(--color-text-muted) 22%, transparent);
	}
	[data-size='md'] .stage-rail-bar {
		height: 0.5rem;
	}
	.stage-rail-step[data-state='done'] .stage-rail-bar {
		background: var(--color-status-success);
	}
	.stage-rail-step[data-state='failed'] .stage-rail-bar {
		background: var(--color-status-error);
	}
	.stage-rail-step[data-state='partial'] .stage-rail-bar {
		background: repeating-linear-gradient(
			-45deg,
			var(--color-status-waiting) 0 4px,
			color-mix(in srgb, var(--color-status-waiting) 25%, transparent) 4px 8px
		);
	}
	.stage-rail-fill {
		position: absolute;
		inset: 0 auto 0 0;
		width: var(--fill-width);
		border-radius: inherit;
		background: var(--hue);
		transition: width 0.4s ease;
	}
	.stage-rail-step[data-state='attention'] .stage-rail-label {
		color: var(--rail-text-waiting);
	}
	.stage-rail-step[data-state='attention'] .stage-rail-bar {
		background: var(--color-status-waiting);
	}
	.stage-rail-fill[data-known='false'] {
		animation: stage-rail-breathe 1.8s ease-in-out infinite;
	}
	@media (prefers-reduced-motion: reduce) {
		.stage-rail-fill[data-known='false'] {
			animation: none;
			opacity: 0.6;
		}
	}
	.stage-rail-label {
		font-size: 0.625rem;
		line-height: 1;
		font-weight: 600;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--rail-text-pending);
	}
	[data-size='md'] .stage-rail-label {
		font-size: 0.6875rem;
	}
	.stage-rail-step[data-state='done'] .stage-rail-label {
		color: var(--rail-text-quiet);
	}
	.stage-rail-step[data-state='active'] .stage-rail-label {
		color: var(--color-text);
		font-weight: 700;
	}
	.stage-rail-step[data-state='failed'] .stage-rail-label {
		color: var(--rail-text-error);
	}
	.stage-rail-step[data-state='partial'] .stage-rail-label {
		color: var(--rail-text-waiting);
	}
	.stage-rail-readout {
		margin-top: 0.5rem;
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 0.75rem;
		font-size: 0.75rem;
		line-height: 1rem;
	}
	.stage-rail-readout-label {
		font-weight: 600;
		color: var(--color-text);
	}
	[data-tone='success'] .stage-rail-readout-label {
		color: var(--rail-text-success);
	}
	[data-tone='warning'] .stage-rail-readout-label {
		color: var(--rail-text-waiting);
	}
	[data-tone='error'] .stage-rail-readout-label {
		color: var(--rail-text-error);
	}
	.stage-rail-readout-detail {
		margin-left: 0.25rem;
		color: var(--rail-text-quiet);
	}
	.stage-rail-figure {
		flex-shrink: 0;
		font-family: var(--font-mono);
		color: var(--rail-text-quiet);
	}
</style>
