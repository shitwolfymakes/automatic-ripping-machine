// The sidebar and drawer nav items, plus the rules that hide items and mark
// the active one. Pure data and functions; the layout supplies the store
// values.
import { isScreenEnabled } from '$lib/features';

export interface NavItem {
	href: string;
	label: string;
	icon: string;
}

export const NAV_ITEMS: readonly NavItem[] = [
	{
		href: '/',
		label: 'Dashboard',
		icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6'
	},
	{
		href: '/notifications',
		label: 'Notifications',
		icon: 'M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9'
	},
	{
		href: '/logs',
		label: 'Logs',
		icon: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z'
	},
	{
		href: '/files',
		label: 'Files',
		icon: 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z'
	},
	{
		href: '/transcoder',
		label: 'Transcoder',
		icon: 'M7 4V2a1 1 0 012 0v2h6V2a1 1 0 012 0v2h1a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h1zm0 8h10m-10 4h6'
	},
	{
		href: '/settings',
		label: 'Settings',
		icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z'
	},
	{
		href: '/help',
		label: 'Help',
		icon: 'M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z'
	}
];

export function visibleNavItems(
	items: readonly NavItem[],
	opts: { transcoderEnabled: boolean; isGuest: boolean }
): NavItem[] {
	return items
		.filter((i) => isScreenEnabled(i.href))
		.filter((i) => i.href !== '/transcoder' || opts.transcoderEnabled)
		.filter((i) => i.href !== '/settings' || !opts.isGuest);
}

export function isActive(href: string, pathname: string): boolean {
	if (href === '/') return pathname === '/';
	return pathname.startsWith(href);
}
