<script lang="ts">
	import type { ChannelStatus } from '../../notifications/channel-helpers';

	let { status }: { status: ChannelStatus } = $props();
</script>

<span class="status-dot" data-status={status} title={status} aria-label={status}></span>
