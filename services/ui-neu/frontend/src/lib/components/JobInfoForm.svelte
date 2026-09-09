<script lang="ts">
	import type { JobView } from '$lib/types/api.gen';
	import { resolveJob } from '$lib/api/jobs';
	import { reveal } from '$lib/transitions';
	import { isAdmin } from '$lib/stores/auth';

	interface Props {
		job: JobView;
		onrefresh?: () => void;
	}
	let { job, onrefresh }: Props = $props();

	// Statuses where the backend resolve endpoint accepts an identity edit.
	// Outside these, resolve returns 409 — the form goes read-only.
	const RESOLVABLE = [
		'awaiting_user_id',
		'ripped_awaiting_identify',
		'awaiting_review',
		'identified',
		'ripped',
		'ripped_partial'
	];
	let resolvable = $derived(RESOLVABLE.includes(job.status));

	let title = $state('');
	let year = $state('');
	let discNumber = $state('');
	let discTotal = $state('');
	let touched = $state<{ title?: boolean; year?: boolean; discNumber?: boolean; discTotal?: boolean }>({});
	let saving = $state(false);
	let feedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	let dirty = $derived(Object.values(touched).some(Boolean));

	// Re-seed each field from `job` only when the operator hasn't touched it, so a
	// background dashboard poll can't clobber in-progress edits.
	$effect.pre(() => {
		if (!touched.title) title = job.title ?? '';
		if (!touched.year) year = job.year != null ? String(job.year) : '';
		if (!touched.discNumber) discNumber = job.disc_number != null ? String(job.disc_number) : '';
		if (!touched.discTotal) discTotal = job.disc_total != null ? String(job.disc_total) : '';
	});

	function num(v: string): number | null {
		const t = String(v).trim();
		return t === '' ? null : Number(t);
	}

	async function saveInfo() {
		if (!title.trim()) return;
		saving = true;
		feedback = null;
		try {
			await resolveJob(job.id, {
				title: title.trim(),
				year: num(year),
				disc_number: num(discNumber),
				disc_total: num(discTotal),
				metadata: {}
			});
			touched = {};
			feedback = { type: 'success', message: 'Saved' };
			onrefresh?.();
		} catch (e) {
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Save failed' };
		} finally {
			saving = false;
		}
	}

	function resetInfo() {
		touched = {};
		feedback = null;
	}
</script>

<div class="job-info-form">
	{#if !resolvable}
		<p class="field-help mb-3">
			Identity is locked once the disc is identified. Use Search to re-identify.
		</p>
	{/if}

	<!-- Identity section -->
	<p class="eyebrow mb-2">Identity</p>
	<div class="flex gap-3">
		<label class="field flex-1">
			<span class="field-label job-info-form-small-label">Title</span>
			<input
				aria-label="Title"
				type="text"
				bind:value={title}
				oninput={() => (touched = { ...touched, title: true })}
				disabled={!resolvable}
			/>
		</label>
		<label class="field w-24">
			<span class="field-label job-info-form-small-label">Year</span>
			<input
				aria-label="Year"
				type="number"
				bind:value={year}
				oninput={() => (touched = { ...touched, year: true })}
				disabled={!resolvable}
			/>
		</label>
	</div>

	<!-- Disc section -->
	<p class="eyebrow mb-2 mt-4">Disc</p>
	<div class="flex gap-3">
		<label class="field w-28">
			<span class="field-label job-info-form-small-label">Disc number</span>
			<input
				aria-label="Disc number"
				type="number"
				bind:value={discNumber}
				oninput={() => (touched = { ...touched, discNumber: true })}
				disabled={!resolvable}
				placeholder="-"
			/>
		</label>
		<label class="field w-28">
			<span class="field-label job-info-form-small-label">Disc total</span>
			<input
				aria-label="Disc total"
				type="number"
				bind:value={discTotal}
				oninput={() => (touched = { ...touched, discTotal: true })}
				disabled={!resolvable}
				placeholder="-"
			/>
		</label>
	</div>
	<p class="field-help mt-1.5">
		For multi-disc sets (box sets, TV seasons) set this disc's position. Leave blank for a single disc.
	</p>

	<!-- Save bar (metadata): appears when there are unsaved edits -->
	{#if dirty && resolvable}
		<div class="mt-3 flex items-center gap-2 job-info-form-save-bar">
			{#if $isAdmin}
				<button
					onclick={saveInfo}
					disabled={saving || !title.trim()}
					class="btn btn-primary job-info-form-save-btn"
				>
					{saving ? 'Saving...' : 'Save'}
				</button>
				<button
					onclick={resetInfo}
					disabled={saving}
					class="btn job-info-form-reset-btn"
				>
					Reset
				</button>
			{/if}
			{#if feedback}
				<span in:reveal class="ml-auto job-info-form-feedback" data-tone={feedback.type}>{feedback.message}</span>
			{/if}
		</div>
	{:else if feedback}
		<div class="mt-3 job-info-form-save-bar">
			<span in:reveal class="job-info-form-feedback" data-tone={feedback.type}>{feedback.message}</span>
		</div>
	{/if}
</div>

<style>
	.job-info-form { border-top: 1px solid var(--color-border); padding: 1rem; }
	/* the original labels were text-xs (12px/16px), one size down from
	   field-label's default text-sm (14px/20px) */
	.job-info-form-small-label { font-size: 0.75rem; line-height: 1rem; }
	.job-info-form-save-bar { border-top: 1px solid var(--color-border); padding-top: 0.75rem; }
	/* Save was px-4 py-1.5 (1rem/0.375rem) no border; Reset px-3 py-1.5
	   (0.75rem/0.375rem) with a ring, not .btn's real border */
	.job-info-form-save-btn { border: 0; padding: 0.375rem 1rem; }
	.job-info-form-reset-btn { border: 0; padding: 0.375rem 0.75rem; box-shadow: 0 0 0 1px var(--color-border-strong); color: var(--color-text-secondary); }
	.job-info-form-feedback { font-size: 0.75rem; line-height: 1rem; }
	.job-info-form-feedback[data-tone="success"] { color: var(--color-success); }
	.job-info-form-feedback[data-tone="error"] { color: var(--color-danger); }
</style>
