import { describe, it, expect, afterEach, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/testing/render';
import InterfaceSettings from '../InterfaceSettings.svelte';
import { uiPrefs, setUiPref } from '$lib/stores/ui-prefs';

beforeEach(() => {
	setUiPref('showStats', true);
	setUiPref('dashboardView', 'card');
});
afterEach(() => cleanup());

describe('InterfaceSettings', () => {
	it('toggles the resource stats preference', async () => {
		renderComponent(InterfaceSettings);
		const sw = screen.getByRole('switch', { name: /show resource stats/i });
		expect(sw).toHaveAttribute('aria-checked', 'true');
		await fireEvent.click(sw);
		expect(get(uiPrefs).showStats).toBe(false);
		expect(sw).toHaveAttribute('aria-checked', 'false');
	});

	it('selects the dashboard layout', async () => {
		renderComponent(InterfaceSettings);
		await fireEvent.click(screen.getByRole('radio', { name: /table/i }));
		expect(get(uiPrefs).dashboardView).toBe('table');
		expect(screen.getByRole('radio', { name: /table/i })).toHaveAttribute('aria-checked', 'true');
	});

	it('selects the card layout back', async () => {
		setUiPref('dashboardView', 'table');
		renderComponent(InterfaceSettings);
		await fireEvent.click(screen.getByRole('radio', { name: /cards/i }));
		expect(get(uiPrefs).dashboardView).toBe('card');
	});

	it('links the dashboard layout to the ARM help and shows no link for resource stats', () => {
		renderComponent(InterfaceSettings);
		expect(
			screen.getByRole('link', { name: 'Docs for Default dashboard layout (opens in a new tab)' })
		).toHaveAttribute('href', '/help/guide/web-ui#dashboard');
		expect(screen.queryByRole('link', { name: 'Docs for Resource stats (opens in a new tab)' })).toBeNull();
	});
});
