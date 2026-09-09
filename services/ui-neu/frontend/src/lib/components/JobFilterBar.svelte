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

<div class="cluster">
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
</div>

<style>
	/* the original select auto-sized to its content (no width utility); the
	   shared .field-control forces width: 100%, which would stretch it across
	   the whole filter row since it is the only child here */
	.job-filter-bar-select { width: auto; }
</style>
