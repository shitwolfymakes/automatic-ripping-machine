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

<div class="border-t border-primary/20 p-4 dark:border-primary/20">
	{#if !resolvable}
		<p class="mb-3 text-xs text-gray-500 dark:text-gray-400">
			Identity is locked once the disc is identified — use Search to re-identify.
		</p>
	{/if}

	<!-- Identity section -->
	<p class="mb-2 text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Identity</p>
	<div class="flex gap-3">
		<div class="flex-1">
			<label for="info-title-{job.id}" class="block text-xs font-medium text-gray-600 dark:text-gray-300">Title</label>
			<input
				id="info-title-{job.id}"
				aria-label="Title"
				type="text"
				bind:value={title}
				oninput={() => (touched = { ...touched, title: true })}
				disabled={!resolvable}
				class="mt-1 w-full rounded-md border border-primary/25 bg-primary/5 px-2 py-1.5 text-sm text-gray-900 focus:border-primary focus:outline-hidden focus:ring-1 focus:ring-primary disabled:opacity-50 dark:border-primary/30 dark:bg-primary/10 dark:text-white"
			/>
		</div>
		<div class="w-24">
			<label for="info-year-{job.id}" class="block text-xs font-medium text-gray-600 dark:text-gray-300">Year</label>
			<input
				id="info-year-{job.id}"
				aria-label="Year"
				type="number"
				bind:value={year}
				oninput={() => (touched = { ...touched, year: true })}
				disabled={!resolvable}
				class="mt-1 w-full rounded-md border border-primary/25 bg-primary/5 px-2 py-1.5 text-sm text-gray-900 focus:border-primary focus:outline-hidden focus:ring-1 focus:ring-primary disabled:opacity-50 dark:border-primary/30 dark:bg-primary/10 dark:text-white"
			/>
		</div>
	</div>

	<!-- Disc section -->
	<p class="mb-2 mt-4 text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Disc</p>
	<div class="flex gap-3">
		<div class="w-28">
			<label for="info-discno-{job.id}" class="block text-xs font-medium text-gray-600 dark:text-gray-300">Disc number</label>
			<input
				id="info-discno-{job.id}"
				aria-label="Disc number"
				type="number"
				bind:value={discNumber}
				oninput={() => (touched = { ...touched, discNumber: true })}
				disabled={!resolvable}
				placeholder="—"
				class="mt-1 w-full rounded-md border border-primary/25 bg-primary/5 px-2 py-1.5 text-sm text-gray-900 focus:border-primary focus:outline-hidden focus:ring-1 focus:ring-primary disabled:opacity-50 dark:border-primary/30 dark:bg-primary/10 dark:text-white"
			/>
		</div>
		<div class="w-28">
			<label for="info-disctot-{job.id}" class="block text-xs font-medium text-gray-600 dark:text-gray-300">Disc total</label>
			<input
				id="info-disctot-{job.id}"
				aria-label="Disc total"
				type="number"
				bind:value={discTotal}
				oninput={() => (touched = { ...touched, discTotal: true })}
				disabled={!resolvable}
				placeholder="—"
				class="mt-1 w-full rounded-md border border-primary/25 bg-primary/5 px-2 py-1.5 text-sm text-gray-900 focus:border-primary focus:outline-hidden focus:ring-1 focus:ring-primary disabled:opacity-50 dark:border-primary/30 dark:bg-primary/10 dark:text-white"
			/>
		</div>
	</div>
	<p class="mt-1.5 text-xs text-gray-500 dark:text-gray-400">
		For multi-disc sets (box sets, TV seasons) set this disc's position. Leave blank for a single disc.
	</p>

	<!-- Save bar (metadata): appears when there are unsaved edits -->
	{#if dirty && resolvable}
		<div class="mt-3 flex items-center gap-2 border-t border-primary/10 pt-3 dark:border-primary/15">
			{#if $isAdmin}
				<button
					onclick={saveInfo}
					disabled={saving || !title.trim()}
					class="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-on-primary hover:bg-primary/90 disabled:opacity-50"
				>
					{saving ? 'Saving…' : 'Save'}
				</button>
				<button
					onclick={resetInfo}
					disabled={saving}
					class="rounded-md px-3 py-1.5 text-sm text-gray-600 ring-1 ring-primary/25 hover:bg-primary/5 disabled:opacity-50 dark:text-gray-300 dark:ring-primary/30"
				>
					Reset
				</button>
			{/if}
			{#if feedback}
				<span in:reveal class="ml-auto text-xs {feedback.type === 'success' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}">{feedback.message}</span>
			{/if}
		</div>
	{:else if feedback}
		<div class="mt-3 border-t border-primary/10 pt-3 dark:border-primary/15">
			<span in:reveal class="text-xs {feedback.type === 'success' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}">{feedback.message}</span>
		</div>
	{/if}
</div>
