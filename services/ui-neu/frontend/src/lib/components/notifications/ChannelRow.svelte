<script lang="ts">
	import type { Channel } from '$lib/types/notifications';
	import { ChevronRight, Send, Pencil } from 'lucide-svelte';
	import StatusDot from './StatusDot.svelte';
	import ServiceGlyph from './ServiceGlyph.svelte';
	import Toggle from './Toggle.svelte';
	import { channelStatus, relativeTime, typeLabel } from './channelHelpers';

	let {
		channel,
		serviceName,
		expanded = false,
		ontoggle,
		ontest,
		onexpand,
		onedit
	}: {
		channel: Channel;
		serviceName: string;
		expanded?: boolean;
		ontoggle?: () => void;
		ontest?: () => void;
		onexpand?: () => void;
		onedit?: () => void;
	} = $props();

	const status = $derived(channelStatus(channel));
	const secondary = $derived(
		channel.type === 'bash'
			? `${typeLabel(channel.type)} | ${(channel.config as { script?: string }).script ?? ''} | ${channel.subscribed_events.length} events`
			: `${typeLabel(channel.type)} | ${channel.subscribed_events.length} events`
	);
</script>

<div
	class="list-row"
	role="button"
	tabindex="0"
	onclick={() => onexpand?.()}
	onkeydown={(e) => { if (e.key === 'Enter') onexpand?.(); }}
>
	<div class="list-row-lead">
		<StatusDot {status} />
		{#if channel.type === 'apprise'}
			<ServiceGlyph id={(channel.config as { url?: string }).url ?? channel.name} name={serviceName} />
		{:else}
			<span class="channel-row-type-glyph" data-type={channel.type}>{channel.type === 'webhook' ? '{}' : '$_'}</span>
		{/if}
	</div>

	<div class="list-row-main">
		<p class="truncate">{channel.name}</p>
		<p class="truncate">
			{secondary}{#if channel.last_error}<span class="channel-row-last-error"> | {channel.last_error}</span>{/if}
		</p>
	</div>

	<div class="hidden list-row-meta md:block">
		{relativeTime(channel.last_fired_at)}
	</div>

	<div class="list-row-actions" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()} role="presentation">
		<Toggle checked={channel.enabled} label="Enabled" onchange={() => ontoggle?.()} />
	</div>

	<div class="list-row-actions">
		<button
			type="button"
			aria-label="Send test"
			onclick={(e) => { e.stopPropagation(); ontest?.(); }}
			class="btn btn-icon"
		>
			<Send size={14} />
		</button>
		<button
			type="button"
			aria-label="Edit"
			title="Edit"
			onclick={(e) => { e.stopPropagation(); onedit?.(); }}
			class="btn btn-icon"
		>
			<Pencil size={14} />
		</button>
		<button
			type="button"
			aria-label={expanded ? 'Collapse' : 'Expand'}
			aria-expanded={expanded}
			onclick={(e) => { e.stopPropagation(); onexpand?.(); }}
			class="btn btn-icon"
		>
			<ChevronRight size={16} class="chevron channel-row-chevron" />
		</button>
	</div>
</div>

<style>
	/* the bash/webhook type glyph: a monospace two-char tile, one of two
	   tones. Distinct from the .glyph block's own default tint since these
	   use per-type accent tones, not the shared primary tint. The original's
	   border-white/5 has no token; --color-border is the nearest hairline role. */
	.channel-row-type-glyph { display: inline-flex; align-items: center; justify-content: center; width: 1.75rem; height: 1.75rem; border-radius: var(--radius-md); border: 1px solid var(--color-border); font-family: var(--font-mono); font-size: 0.75rem; }
	/* tone soft backgrounds (the vocabulary's own tinted-surface roles),
	   replacing the earlier ad hoc 20% mixes flagged in Task 9's review */
	.channel-row-type-glyph[data-type="webhook"] { background: var(--color-info-soft); color: var(--color-info); }
	.channel-row-type-glyph[data-type="bash"] { background: var(--color-warning-soft); color: var(--color-warning); }
	/* :global: this class is set on a lucide ChevronRight component instance, which Svelte's scoping can't see. .btn-icon svg and .btn .chevron both force 0.875rem; this expand chevron was 16px (size=16) in the original, not 14px. */
	:global(.channel-row-chevron) { width: 1rem; height: 1rem; }
	.channel-row-last-error { color: var(--color-status-error); }
</style>
