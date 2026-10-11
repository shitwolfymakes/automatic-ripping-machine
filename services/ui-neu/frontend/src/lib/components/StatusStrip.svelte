<script lang="ts">
	import Glyph from '$lib/components/Glyph.svelte';
	import type { GlyphName } from '$lib/components/glyph-names';

	// One-line state of an async thing (enroll, probe, key check): glyph + words,
	// never colour alone. role=status so screen readers hear the change.
	type Tone = 'ok' | 'busy' | 'danger' | 'warning' | 'muted';
	let {
		tone,
		title,
		detail,
		message,
		progress = false
	}: { tone: Tone; title: string; detail?: string | null; message?: string | null; progress?: boolean } = $props();

	const GLYPH: Record<Tone, GlyphName> = {
		ok: 'check-circle',
		busy: 'loader',
		danger: 'x-circle',
		warning: 'warning',
		muted: 'info'
	};
</script>

<div class="status-strip" data-tone={tone} role="status" aria-live="polite">
	<div class="status-strip-line">
		<Glyph name={GLYPH[tone]} class="h-4 w-4 {tone === 'busy' ? 'spin' : ''}" />
		<span class="status-strip-title">{title}</span>
		{#if detail}<span class="status-strip-detail">{detail}</span>{/if}
	</div>
	{#if message}<p class="mono status-strip-message">{message}</p>{/if}
	{#if progress}<div class="status-strip-bar" aria-hidden="true"><span></span></div>{/if}
</div>

<style>
	.status-strip {
		border-radius: var(--radius-md);
		padding: 0.625rem 0.875rem;
		background: var(--color-primary-tint-1);
		color: var(--color-text-muted);
	}
	.status-strip[data-tone='ok'] {
		background: var(--color-success-soft);
		color: var(--color-on-success-soft);
	}
	.status-strip[data-tone='busy'] {
		background: var(--color-primary-tint-2);
		color: var(--color-primary-text);
	}
	.status-strip[data-tone='danger'] {
		background: var(--color-danger-soft);
		color: var(--color-on-danger-soft);
	}
	.status-strip[data-tone='warning'] {
		background: var(--color-warning-soft);
		color: var(--color-on-warning-soft);
	}
	.status-strip-line {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.25rem 0.5rem;
	}
	.status-strip-title {
		font-weight: 600;
	}
	.status-strip-detail {
		font-size: 0.8125rem;
		color: var(--color-text-muted);
	}
	.status-strip-message {
		margin-top: 0.375rem;
		font-size: 0.75rem;
		color: var(--color-text-muted);
		overflow-wrap: anywhere;
		white-space: pre-wrap;
	}
	.status-strip-bar {
		position: relative;
		margin-top: 0.5rem;
		height: 0.1875rem;
		border-radius: 999px;
		background: var(--color-primary-tint-3);
		overflow: hidden;
	}
	.status-strip-bar span {
		position: absolute;
		inset: 0 auto 0 0;
		width: 40%;
		border-radius: inherit;
		background: var(--color-primary);
		animation: status-strip-slide 1.4s ease-in-out infinite;
	}
	@keyframes status-strip-slide {
		from {
			transform: translateX(-100%);
		}
		to {
			transform: translateX(250%);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.status-strip-bar span {
			animation: none;
			width: 100%;
			opacity: 0.4;
		}
	}
</style>
