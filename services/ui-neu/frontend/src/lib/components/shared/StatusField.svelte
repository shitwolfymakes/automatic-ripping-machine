<script lang="ts">
	// A labelled one-line state, such as the MakeMKV key status or whether this
	// deployment can transcode: a small caps label over a StatusStrip.
	import StatusStrip from '$lib/components/shared/StatusStrip.svelte';

	type Tone = 'ok' | 'busy' | 'danger' | 'warning' | 'muted';
	let { label, tone, title, message }: { label: string; tone: Tone; title: string; message?: string | null } = $props();
</script>

<div class="status-field">
	<span class="status-field-label">{label}</span>
	<StatusStrip {tone} {title} {message} />
</div>

<style>
	.status-field {
		display: grid;
		gap: 0.25rem;
	}
	.status-field-label {
		font-size: 0.75rem;
		font-weight: 600;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: var(--color-text-faint);
	}
</style>
