import { describe, it, expect } from 'vitest';
import { JobPanels } from '$lib/stores/job-panels.svelte';

describe('JobPanels', () => {
	it('starts with no panel open and no initial search type', () => {
		const panels = new JobPanels();
		expect(panels.active).toBeNull();
		expect(panels.titleInitialType).toBeUndefined();
	});

	it('opens a panel when toggled and closes it when toggled again', () => {
		const panels = new JobPanels();
		panels.toggle('music');
		expect(panels.active).toBe('music');
		panels.toggle('music');
		expect(panels.active).toBeNull();
	});

	it('switches to another panel when a different one is toggled', () => {
		const panels = new JobPanels();
		panels.toggle('music');
		panels.toggle('episodes');
		expect(panels.active).toBe('episodes');
	});

	it('clears the initial search type when the title panel is toggled', () => {
		const panels = new JobPanels();
		panels.titleInitialType = 'tv';
		panels.toggle('title');
		expect(panels.titleInitialType).toBeUndefined();
		expect(panels.active).toBe('title');
	});

	it('keeps the initial search type when another panel is toggled', () => {
		const panels = new JobPanels();
		panels.titleInitialType = 'tv';
		panels.toggle('episodes');
		expect(panels.titleInitialType).toBe('tv');
	});

	it('searchSeries sets the tv search type and opens the title panel', () => {
		const panels = new JobPanels();
		panels.toggle('episodes');
		panels.searchSeries();
		expect(panels.titleInitialType).toBe('tv');
		expect(panels.active).toBe('title');
	});
});
