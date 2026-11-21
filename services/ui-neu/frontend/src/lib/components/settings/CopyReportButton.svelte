<script lang="ts">
	import { addToast } from '$lib/stores/toast.svelte';

	interface Props {
		getReport: () => Promise<string>;
	}

	let { getReport }: Props = $props();

	let busy = $state(false);
	let fallback = $state<string | null>(null);
	let area = $state<HTMLTextAreaElement | undefined>();

	async function copy(): Promise<void> {
		busy = true;
		try {
			const report = await getReport();
			try {
				if (!navigator.clipboard) throw new Error('no clipboard');
				await navigator.clipboard.writeText(report);
				addToast({ tone: 'success', title: 'Deployment report copied' });
			} catch {
				fallback = report;
			}
		} catch (e) {
			addToast({
				tone: 'error',
				title: 'Could not build the report',
				body: e instanceof Error ? e.message : undefined
			});
		} finally {
			busy = false;
		}
	}

	$effect(() => {
		if (fallback !== null && area) {
			area.focus();
			area.select();
		}
	});
</script>

<button type="button" class="btn" disabled={busy} onclick={copy}>Copy deployment report</button>

{#if fallback !== null}
	<div class="modal">
		<button
			type="button"
			class="copy-report-scrim absolute inset-0"
			aria-label="Close dialog"
			onclick={() => (fallback = null)}
		></button>
		<div
			class="modal-panel copy-report-panel relative"
			role="dialog"
			aria-modal="true"
			aria-labelledby="copy-report-title"
		>
			<h3 id="copy-report-title" class="modal-title">Copy deployment report</h3>
			<p class="modal-body">Clipboard access is unavailable. Select all and copy the report below.</p>
			<textarea class="input copy-report-text mono" readonly value={fallback} bind:this={area}></textarea>
			<div class="modal-actions">
				<button type="button" class="btn btn-primary" onclick={() => (fallback = null)}>Close</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.copy-report-scrim {
		z-index: 0;
		background: transparent;
		border: 0;
		cursor: default;
	}
	.copy-report-panel {
		z-index: 1;
	}
	.copy-report-text {
		width: 100%;
		height: 16rem;
		font-size: 0.75rem;
	}
</style>
