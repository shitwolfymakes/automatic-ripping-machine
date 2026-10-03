<script lang="ts">
	import { isGuest } from '$lib/stores/auth';
	import { dashboard } from '$lib/stores/dashboard';
	import { countRipping } from '$lib/utils/job-status';
	import SidebarStats from './SidebarStats.svelte';

	interface Props {
		/** Called when any link inside the panel is clicked (so the drawer can close). */
		onnavigate?: () => void;
	}

	let { onnavigate }: Props = $props();

	const rippingCount = $derived(countRipping($dashboard.active_jobs ?? []));

	// Links inside SidebarStats (storage rows) must also close the drawer, so
	// catch link clicks at the panel root instead of per-anchor. Keyboard
	// activation of a link fires a click event too, so no keydown handler is
	// needed here.
	function handleClick(e: MouseEvent) {
		if ((e.target as Element).closest('a')) onnavigate?.();
	}

	const services = $derived([
		{
			label: 'ARM',
			href: '/settings#system',
			status: $dashboard.arm_online ? 'ok' : 'error'
		},
		{
			label: 'DB',
			href: '/settings#system',
			status: $dashboard.db_available ? 'ok' : 'warn'
		},
		{
			label: 'Transcode',
			href: '/transcoder',
			status:
				$dashboard.transcoder_online && ($dashboard.transcoder_stats?.worker_running ?? true)
					? 'ok'
					: $dashboard.transcoder_online
						? 'warn'
						: 'off'
		},
		{
			label: 'Key',
			href: '/settings#Metadata/makemkv_key',
			status: $dashboard.makemkv_key_valid === true ? 'ok' : 'error'
		}
	]);
</script>

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div data-mobile-stats class="mobile-stats flex-1 overflow-y-auto" onclick={handleClick}>
	<div class="mobile-stats-section">
		<p class="eyebrow mobile-stats-heading">
			Services
		</p>
		<div class="stack stack-sm mobile-stats-list">
			{#each services as s (s.label)}
				{@const linked = !$isGuest || !s.href.startsWith('/settings')}
				<svelte:element
					this={linked ? 'a' : 'span'}
					href={linked ? s.href : undefined}
					class="nav-item mobile-stats-row"
				>
					<span class="status-dot" data-status={s.status}></span>
					{s.label}
				</svelte:element>
			{/each}
		</div>
	</div>

	<hr class="mobile-stats-hr" />

	<div class="mobile-stats-section">
		<p class="eyebrow mobile-stats-heading">
			Activity
		</p>
		<div class="stack stack-sm mobile-stats-list mobile-stats-activity">
			<svelte:element
				this={$isGuest ? 'span' : 'a'}
				href={$isGuest ? undefined : '/settings#drives'}
				class="nav-item mobile-stats-row"
			>
				{$dashboard.db_available ? $dashboard.drives_online : '--'} drive{$dashboard.drives_online !== 1 ? 's' : ''}
			</svelte:element>
			{#if rippingCount > 0}
				<p class="nav-item mobile-stats-ripping">{rippingCount} ripping</p>
			{/if}
			{#if $dashboard.active_transcodes.length > 0}
				<a
					href="/transcoder"
					class="nav-item mobile-stats-transcoding"
				>
					{$dashboard.active_transcodes.length} transcoding
				</a>
			{/if}
			{#if $dashboard.transcoder_online && (Number($dashboard.transcoder_stats?.pending) || 0) > 0}
				<p class="nav-item mobile-stats-queued">
					{$dashboard.transcoder_stats?.pending} queued
				</p>
			{/if}
			{#if ($dashboard.notification_count ?? 0) > 0}
				<a
					href="/notifications"
					class="nav-item mobile-stats-notification"
				>
					{$dashboard.notification_count} notification{$dashboard.notification_count !== 1 ? 's' : ''}
				</a>
			{/if}
		</div>
	</div>

	<SidebarStats />
</div>

<style>
	.mobile-stats {
		font-variant-numeric: tabular-nums;
	}
	/* .stack-sm is 0.5rem; the original space-y-1 lists here were 0.25rem. */
	.mobile-stats-list {
		gap: 0.25rem;
	}
	.mobile-stats-section {
		padding: 1rem 0.75rem;
	}
	.mobile-stats-heading {
		margin-bottom: 0.5rem;
		padding: 0 0.75rem;
		/* The eyebrow block is 11px/0.12em; these panel headings have always
		   been 10px/0.05em, and the extra height shifts every row below them. */
		font-size: 10px;
		line-height: 1.5;
		letter-spacing: 0.05em;
		color: var(--color-text-faint);
	}
	.mobile-stats-row {
		font-weight: 500;
	}
	/* This panel's service dots are 10px, a size up from the status-dot
	   block's default 8px. */
	.mobile-stats-row .status-dot {
		width: 0.625rem;
		height: 0.625rem;
	}
	.mobile-stats-hr {
		border-top: 1px solid var(--color-border);
	}
	.mobile-stats-activity {
		font-size: 0.875rem;
	}
	/* Four distinct count tones, not one, off the existing status/tone roles
	   these states already fill their dots and bars with (same mapping as the
	   desktop header's .layout-activity-* rules). */
	.mobile-stats-ripping {
		font-weight: 600;
		color: var(--color-status-ripping);
	}
	.mobile-stats-transcoding {
		font-weight: 600;
		color: var(--color-status-transcoding);
	}
	.mobile-stats-queued {
		font-weight: 600;
		color: var(--color-status-waiting);
	}
	.mobile-stats-notification {
		font-weight: 600;
		color: var(--color-warning);
	}
</style>
