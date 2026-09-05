import { describe, it, expect, afterEach, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import InterfaceSettings from '../InterfaceSettings.svelte';
import { uiPrefs, setUiPref } from '$lib/stores/uiPrefs';

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
});
