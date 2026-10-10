<script lang="ts">
	import { statusColor, statusLabel } from '$lib/utils/format';

	interface Props {
		status: string | null | undefined;
	}

	let { status }: Props = $props();

	// statusColor() buckets the many backend status strings into the small
	// status-* vocabulary badge.css keys its [data-status] rules off; strip
	// the "status-" prefix to get the bare data-status token.
	let dataStatus = $derived(statusColor(status).replace(/^status-/, ''));
</script>

<span class="badge badge-status status-badge" data-status={dataStatus}>
	{statusLabel(status)}
</span>

<style>
	/* the .badge block's horizontal padding (0.5rem) is tighter than this
	   component's original px-2.5 (0.625rem). */
	.status-badge { padding-left: 0.625rem; padding-right: 0.625rem; }
</style>
