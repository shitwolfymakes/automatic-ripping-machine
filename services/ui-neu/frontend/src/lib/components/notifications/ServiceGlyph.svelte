<script lang="ts">
	let { id, name, size = 28 }: { id: string; name: string; size?: number } = $props();

	// Deterministic hue from the service id.
	function hue(s: string): number {
		let h = 0;
		for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360;
		return h;
	}

	const h = $derived(hue(id));
	const bg = $derived(`oklch(0.45 0.13 ${h})`);
	const fg = $derived(`oklch(0.78 0.16 ${h})`);
	const letter = $derived((name?.[0] ?? '?').toUpperCase());
</script>

<span
	data-glyph
	class="service-glyph"
	style:--size="{size}px"
	style:--font-size="{Math.round(size * 0.45)}px"
	style:--bg={bg}
	style:--fg={fg}
	aria-hidden="true"
>{letter}</span>

<style>
	.service-glyph {
		display: inline-flex;
		flex-shrink: 0;
		align-items: center;
		justify-content: center;
		width: var(--size);
		height: var(--size);
		font-size: var(--font-size);
		border-radius: var(--radius-md);
		/* the glyph sits on its own coloured --bg, so the hairline is the
		   on-primary white rather than a surface or border token. */
		border: 1px solid color-mix(in srgb, var(--color-on-primary) 5%, transparent);
		font-weight: 700;
		background: var(--bg);
		color: var(--fg);
	}
</style>
