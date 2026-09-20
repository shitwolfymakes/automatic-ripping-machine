import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import TrackFiltersEditor from '../TrackFiltersEditor.svelte';

afterEach(() => {
	cleanup();
});

const baseValue = {
	min_duration_seconds: 60,
	max_duration_seconds: 600,
	title_indices: [1, 2],
	title_indices_exclude: [9]
};

describe('TrackFiltersEditor', () => {
	it('renders inputs seeded from value', () => {
		renderComponent(TrackFiltersEditor, {
			props: { value: baseValue, onchange: vi.fn() }
		});
		expect(screen.getByTestId('tf-min-duration')).toHaveValue(60);
		expect(screen.getByTestId('tf-max-duration')).toHaveValue(600);
		expect(screen.getByTestId('tf-allowlist')).toHaveValue('1, 2');
		expect(screen.getByTestId('tf-blocklist')).toHaveValue('9');
	});

	it('parses comma-separated allowlist and preserves other keys', async () => {
		const onchange = vi.fn();
		renderComponent(TrackFiltersEditor, {
			props: { value: baseValue, onchange }
		});
		await fireEvent.input(screen.getByTestId('tf-allowlist'), {
			target: { value: '1, 3, 5' }
		});
		expect(onchange).toHaveBeenCalledWith({
			...baseValue,
			title_indices: [1, 3, 5]
		});
	});

	it('parses space-separated blocklist', async () => {
		const onchange = vi.fn();
		renderComponent(TrackFiltersEditor, {
			props: { value: baseValue, onchange }
		});
		await fireEvent.input(screen.getByTestId('tf-blocklist'), {
			target: { value: '2 4' }
		});
		expect(onchange).toHaveBeenCalledWith({
			...baseValue,
			title_indices_exclude: [2, 4]
		});
	});

	it('clearing a list input sets that key to null', async () => {
		const onchange = vi.fn();
		renderComponent(TrackFiltersEditor, {
			props: { value: baseValue, onchange }
		});
		await fireEvent.input(screen.getByTestId('tf-allowlist'), {
			target: { value: '' }
		});
		expect(onchange).toHaveBeenCalledWith({
			...baseValue,
			title_indices: null
		});
	});

	it('sets min duration to the number when filled', async () => {
		const onchange = vi.fn();
		renderComponent(TrackFiltersEditor, {
			props: { value: baseValue, onchange }
		});
		await fireEvent.input(screen.getByTestId('tf-min-duration'), {
			target: { value: '120' }
		});
		expect(onchange).toHaveBeenCalledWith({
			...baseValue,
			min_duration_seconds: 120
		});
	});

	it('sets min duration to null when blank', async () => {
		const onchange = vi.fn();
		renderComponent(TrackFiltersEditor, {
			props: { value: baseValue, onchange }
		});
		await fireEvent.input(screen.getByTestId('tf-min-duration'), {
			target: { value: '' }
		});
		expect(onchange).toHaveBeenCalledWith({
			...baseValue,
			min_duration_seconds: null
		});
	});

	it('filters out non-positive and non-integer entries', async () => {
		const onchange = vi.fn();
		renderComponent(TrackFiltersEditor, {
			props: { value: baseValue, onchange }
		});
		await fireEvent.input(screen.getByTestId('tf-allowlist'), {
			target: { value: '0, -1, 2, x' }
		});
		expect(onchange).toHaveBeenCalledWith({
			...baseValue,
			title_indices: [2]
		});
	});
});
