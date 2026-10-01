<script lang="ts">
	import Glyph from '$lib/components/Glyph.svelte';

	// A shell command (or env line) the operator runs on the server, with a copy
	// button. Shared by Settings > System and the setup walkthrough.
	let { text, label = 'Copy' }: { text: string; label?: string } = $props();

	let copyState = $state<'idle' | 'copied' | 'manual'>('idle');
	let codeEl: HTMLElement | undefined = $state();
	let resetTimer: ReturnType<typeof setTimeout> | null = null;

	async function copy() {
		try {
			await navigator.clipboard.writeText(text);
			copyState = 'copied';
		} catch {
			// No clipboard access (http, permissions): select the text instead.
			if (codeEl) {
				const range = document.createRange();
				range.selectNodeContents(codeEl);
				const sel = window.getSelection();
				sel?.removeAllRanges();
				sel?.addRange(range);
			}
			copyState = 'manual';
		}
		if (resetTimer) clearTimeout(resetTimer);
		resetTimer = setTimeout(() => (copyState = 'idle'), 2000);
	}
</script>

<div class="copy-block" data-testid="copy-block">
	<code class="mono copy-block-text" bind:this={codeEl}>{text}</code>
	<button type="button" class="btn btn-sm copy-block-btn" onclick={copy} aria-label="{label}: {text}">
		<Glyph name={copyState === 'copied' ? 'check' : 'copy'} />
		<span aria-live="polite">{copyState === 'copied' ? 'Copied' : copyState === 'manual' ? 'Press Ctrl+C' : label}</span
		>
	</button>
</div>

<style>
	.copy-block {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-primary-tint-1);
		padding: 0.5rem 0.5rem 0.5rem 0.875rem;
	}
	.copy-block-text {
		flex: 1 1 auto;
		min-width: 0;
		font-size: 0.8125rem;
		color: var(--color-text);
		overflow-wrap: anywhere;
		white-space: pre-wrap;
	}
	.copy-block-btn {
		flex: none;
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
	}
</style>
