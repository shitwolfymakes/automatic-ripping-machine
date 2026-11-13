<script lang="ts">
	import { plural } from '$lib/utils/plural';
	import type { Snippet } from 'svelte';
	import { dashboard } from '$lib/stores/dashboard';
	import { isGuest } from '$lib/stores/auth';
	import { countRipping } from '$lib/utils/job-status';
	import { transcoderDotStatus, makemkvKeyTitle } from '$lib/utils/header-status';

	const rippingCount = $derived(countRipping($dashboard.active_jobs ?? []));
</script>

{#snippet guestLink(href: string, cls: string, content: Snippet, title?: string)}
	<!-- A guest sees a plain span; everyone else gets a link. -->
	<svelte:element this={$isGuest ? 'span' : 'a'} href={$isGuest ? undefined : href} class={cls} {title}
		>{@render content()}</svelte:element
	>
{/snippet}

{#snippet armHealth()}
	<span class="status-dot" data-status={$dashboard.arm_online ? 'ok' : 'error'}></span>
	<span class="layout-health-label">ARM</span>
{/snippet}

{#snippet dbHealth()}
	<span class="status-dot" data-status={$dashboard.db_available ? 'ok' : 'warn'}></span>
	<span class="layout-health-label">DB</span>
{/snippet}

{#snippet keyHealth()}
	<span class="status-dot" data-status={$dashboard.makemkv_key_valid === true ? 'ok' : 'error'}></span>
	<span class="layout-health-label">Key</span>
{/snippet}

{#snippet driveCount()}
	{$dashboard.db_available ? $dashboard.drives_online : '--'} {plural($dashboard.drives_online, 'drive')}
{/snippet}

<div class="layout-stats-bar hidden lg:flex items-center gap-3">
	<!-- Service health dots -->
	<div class="flex items-center gap-3">
		{@render guestLink('/settings#system', 'layout-health-link', armHealth)}
		{@render guestLink('/settings#system', 'layout-health-link', dbHealth)}
		<a href="/transcoder" class="layout-health-link">
			<span class="status-dot" data-status={transcoderDotStatus($dashboard)}></span>
			<span class="layout-health-label">Transcode</span>
		</a>
		{@render guestLink(
			'/settings#Keys/makemkv_key',
			'layout-health-link',
			keyHealth,
			makemkvKeyTitle($dashboard.makemkv_key_valid, $dashboard.makemkv_key_checked_at)
		)}
	</div>
	<!-- Divider -->
	<div class="layout-header-divider"></div>
	<!-- Live activity -->
	<div class="layout-activity-group flex items-center gap-3">
		{@render guestLink('/settings#drives', 'layout-activity-link', driveCount)}
		{#if rippingCount > 0}
			<span class="layout-activity-ripping">{rippingCount} ripping</span>
		{/if}
		{#if $dashboard.active_transcodes.length > 0}
			<a href="/transcoder" class="layout-activity-transcoding">{$dashboard.active_transcodes.length} transcoding</a>
		{/if}
		{#if $dashboard.transcoder_online && (Number($dashboard.transcoder_stats?.pending) || 0) > 0}
			<span class="layout-activity-queued">{$dashboard.transcoder_stats?.pending} queued</span>
		{/if}
		{#if ($dashboard.notification_count ?? 0) > 0}
			<a href="/notifications" class="layout-activity-notification"
				>{$dashboard.notification_count} {plural($dashboard.notification_count, 'notification')}</a
			>
		{/if}
	</div>
</div>

<style>
	.layout-stats-bar {
		font-size: 0.875rem;
	}
	.layout-activity-group {
		font-size: 0.75rem;
	}
	.layout-header-divider {
		height: 1.5rem;
		width: 1px;
		background: var(--color-border-strong);
	}
	/* Service health dots: label + hover affordance shared by all four rows. */
	.layout-health-link {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		transition: opacity var(--motion-fast) var(--ease);
	}
	a.layout-health-link:hover {
		opacity: 0.75;
	}
	.layout-health-label {
		color: var(--color-text-secondary);
	}
	.layout-activity-link {
		color: var(--color-text-muted);
		transition: color var(--motion-fast) var(--ease);
	}
	a.layout-activity-link:hover {
		color: var(--color-primary-text);
	}
	/* Four distinct count tones. These are TEXT labels, so they take the
	   accent roles that match their originals (blue-400, indigo-400,
	   amber-400), not the --color-status-* machine that fills dots and
	   progress bars: a scheme is free to redefine the status colours for its
	   own state machine (winamp-97 sets every one of them to terminal green),
	   which would collapse all four counts into one colour. */
	.layout-activity-ripping {
		font-weight: 600;
		color: var(--color-accent-2);
	}
	.layout-activity-transcoding {
		font-weight: 600;
		color: var(--color-accent-3);
	}
	.layout-activity-queued {
		font-weight: 600;
		color: var(--color-accent-1);
	}
	.layout-activity-notification {
		font-weight: 600;
		color: var(--color-warning);
	}
	a.layout-activity-transcoding:hover,
	a.layout-activity-notification:hover {
		color: var(--color-primary-hover);
	}
</style>
