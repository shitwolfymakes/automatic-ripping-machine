<script lang="ts">
	// v3 GET /api/jobs supports a single `status` filter (JobStatus). The BFF's
	// free-text search + video_type / disctype / days filters have no v3
	// equivalent and were dropped.
	interface Props {
		statusFilter: string;
		onstatusfilter: (value: string) => void;
	}

	let { statusFilter, onstatusfilter }: Props = $props();
</script>

<select
	value={statusFilter}
	onchange={(e) => onstatusfilter((e.target as HTMLSelectElement).value)}
	class="field-control job-filter-bar-select"
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

<style>
	/* the shared .field-control forces width: 100%; this select sits inline in
	   the jobs panel header, so it sizes to its content instead */
	.job-filter-bar-select {
		width: auto;
	}
</style>
