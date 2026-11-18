<script lang="ts">
	import NotificationsTab from '$lib/components/notifications/NotificationsTab.svelte';
	import Toggle from '$lib/components/shared/Toggle.svelte';

	interface Props {
		enabled: boolean;
		ontoggle: (next: boolean) => void;
	}

	let { enabled, ontoggle }: Props = $props();
</script>

<div class="stack" data-page-section>
	<div>
		<h2 class="settings-page-section-title" data-page-section-title>Notifications</h2>
		<p class="settings-page-description">Manage notification channels - Discord, Slack, webhooks, scripts, and more.</p>
	</div>
	<label class="field field-row settings-page-notif-toggle-row">
		<Toggle checked={enabled} label="Enable notifications" onchange={ontoggle} />
		<span class="field-label">Enable notifications</span>
		<span class="settings-page-inline-hint">(changes save automatically)</span>
	</label>
	{#if enabled}
		<NotificationsTab />
	{:else}
		<p class="panel-section settings-page-notifications-off">
			Notifications are disabled. Enable the toggle above to manage channels.
		</p>
	{/if}
</div>

<style>
	.settings-page-section-title {
		font-size: 1.125rem;
		line-height: 1.75rem;
		font-weight: 600;
		color: var(--color-text);
	}
	/* most "muted description under a heading" paragraphs on this page were
	   text-sm (0.875rem/1.25rem), not panel-hint's 0.75rem - panel-hint is
	   sized for a note under a form control, a visibly smaller role. */
	.settings-page-description {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	.settings-page-notifications-off {
		text-align: center;
		padding: 1.5rem 1rem;
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	/* text-xs text-gray-500 - a plain inline span in the toggle row, not
	   panel-hint's block-level note (whose own margin-top would misalign
	   it against its row siblings). */
	.settings-page-inline-hint {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-muted);
	}
	/* the original toggle row was gap-3 (0.75rem), not field-row's 0.5rem. */
	.settings-page-notif-toggle-row {
		gap: 0.75rem;
	}
</style>
