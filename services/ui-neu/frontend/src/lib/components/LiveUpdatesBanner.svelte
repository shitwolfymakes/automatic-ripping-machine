<!-- G-28: a visible "live updates unavailable" state instead of the WS
     client's silent reconnect loop. Shows only after the connection has
     failed repeatedly (wsStatus 'offline'), stays until a connection
     authenticates, and never renders while the socket is idle or merely
     reconnecting from a blip. -->
<script lang="ts">
	import { wsStatus } from '$lib/api/ws';
</script>

{#if $wsStatus === 'offline'}
	<div class="alert alert-warning live-updates-banner" role="status">
		<div class="alert-title">Live updates unavailable</div>
		<div class="alert-body">
			The live connection to the server keeps failing, so rip progress and events will not refresh
			until it recovers. Reconnecting in the background; pages still load current data when opened.
			If this persists behind a reverse proxy, add its origin to ARM_ALLOWED_ORIGINS.
		</div>
	</div>
{/if}

<style>
	.live-updates-banner {
		margin-bottom: 1rem;
	}
</style>
