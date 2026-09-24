<script lang="ts">
	// v3 GET /api/jobs supports a single `status` filter (JobStatus). The BFF's
	// free-text search + video_type / disctype / days filters have no v3
	// equivalent and were dropped.
	interface Props {
		statusFilter: string;
		onstatusfilter: (value: string) => void;
	}

	let { statusFilter, onstatusfilter }: Props = $props();

	const selectClasses = 'rounded-lg border border-primary/25 bg-primary/5 px-3 py-2 text-sm dark:border-primary/30 dark:bg-primary/10 dark:text-white';
</script>

<div class="flex flex-wrap items-center gap-3">
	<select
		value={statusFilter}
		onchange={(e) => onstatusfilter((e.target as HTMLSelectElement).value)}
		class={selectClasses}
	>
		<option value="">All Status</option>
		<option value="created">Created</option>
		<option value="awaiting_user_id">Awaiting ID</option>
		<option value="awaiting_review">Ready: review</option>
		<option value="identified">Identified</option>
		<option value="ripping">Ripping</option>
		<option value="ripped">Ripped</option>
		<option value="ripped_partial">Ripped (partial)</option>
		<option value="ripped_awaiting_identify">Ripped (awaiting ID)</option>
		<option value="abandoned">Abandoned</option>
		<option value="failed">Failed</option>
	</select>
</div>
