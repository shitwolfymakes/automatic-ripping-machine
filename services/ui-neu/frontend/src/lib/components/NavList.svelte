<script lang="ts">
	import { isActive, type NavItem } from '$lib/nav';

	let {
		items,
		pathname,
		notificationCount,
		onnavigate
	}: {
		items: NavItem[];
		pathname: string;
		notificationCount: number | null;
		onnavigate?: () => void;
	} = $props();
</script>

<nav class="nav flex-1 overflow-y-auto">
	{#each items as item (item.href)}
		<a href={item.href} onclick={onnavigate} data-active={isActive(item.href, pathname) || undefined} class="nav-item">
			<svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={item.icon} />
			</svg>
			{item.label}
			{#if item.href === '/notifications' && (notificationCount ?? 0) > 0}
				<span class="nav-badge">{notificationCount}</span>
			{/if}
		</a>
	{/each}
</nav>
