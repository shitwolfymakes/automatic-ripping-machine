import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import TrackFiltersEditor from '../TrackFiltersEditor.svelte';

// Branch pins for TrackFiltersEditor, beside TrackFiltersEditor.test.ts. Every
// branch is reachable from the rendered inputs, so nothing here is forced.

afterEach(() => {
	cleanup();
});

const baseValue = {
	min_duration_seconds: 60,
	max_duration_seconds: 600,
	title_indices: [1, 2],
	title_indices_exclude: [9]
};

async function typeInto(testId: string, text: string, value = baseValue) {
	const onchange = vi.fn();
	renderComponent(TrackFiltersEditor, { props: { value, onchange } });
	await fireEvent.input(screen.getByTestId(testId), { target: { value: text } });
	return onchange;
}

describe('TrackFiltersEditor durations', () => {
	it('sets max duration to the number and keeps the other keys', async () => {
		const onchange = await typeInto('tf-max-duration', '900');
		expect(onchange).toHaveBeenCalledWith({ ...baseValue, max_duration_seconds: 900 });
	});

	it('sets max duration to null when blank', async () => {
		const onchange = await typeInto('tf-max-duration', '');
		expect(onchange).toHaveBeenCalledWith({ ...baseValue, max_duration_seconds: null });
	});
});

describe('TrackFiltersEditor index lists', () => {
	it.each([
		['tf-allowlist', 'title_indices'],
		['tf-blocklist', 'title_indices_exclude']
	])('%s splits on commas, spaces and both mixed', async (testId, key) => {
		expect(await typeInto(testId, '1,3')).toHaveBeenLastCalledWith({ ...baseValue, [key]: [1, 3] });
		cleanup();
		expect(await typeInto(testId, '1 3')).toHaveBeenLastCalledWith({ ...baseValue, [key]: [1, 3] });
		cleanup();
		expect(await typeInto(testId, '1, 3  5,7')).toHaveBeenLastCalledWith({
			...baseValue,
			[key]: [1, 3, 5, 7]
		});
	});

	it.each([
		['tf-allowlist', 'title_indices'],
		['tf-blocklist', 'title_indices_exclude']
	])('%s keeps positive integers only', async (testId, key) => {
		const onchange = await typeInto(testId, '0, -2, 1.5, abc, 4');
		expect(onchange).toHaveBeenCalledWith({ ...baseValue, [key]: [4] });
	});

	it.each([
		['tf-allowlist', 'title_indices'],
		['tf-blocklist', 'title_indices_exclude']
	])('%s sets null when empty or when nothing survives parsing', async (testId, key) => {
		expect(await typeInto(testId, '')).toHaveBeenLastCalledWith({ ...baseValue, [key]: null });
		cleanup();
		expect(await typeInto(testId, '0, -1, 1.5, x')).toHaveBeenLastCalledWith({
			...baseValue,
			[key]: null
		});
	});
});

describe('TrackFiltersEditor shown text', () => {
	it('joins each list with ", "', () => {
		renderComponent(TrackFiltersEditor, {
			props: {
				value: { title_indices: [1, 3, 5], title_indices_exclude: [2, 4] },
				onchange: vi.fn()
			}
		});
		expect(screen.getByTestId('tf-allowlist')).toHaveValue('1, 3, 5');
		expect(screen.getByTestId('tf-blocklist')).toHaveValue('2, 4');
	});

	it('shows empty inputs when the lists and durations are missing', () => {
		renderComponent(TrackFiltersEditor, { props: { value: {}, onchange: vi.fn() } });
		expect(screen.getByTestId('tf-allowlist')).toHaveValue('');
		expect(screen.getByTestId('tf-blocklist')).toHaveValue('');
		expect(screen.getByTestId('tf-min-duration')).toHaveValue(null);
		expect(screen.getByTestId('tf-max-duration')).toHaveValue(null);
	});

	it('shows empty inputs when the lists and durations are null', () => {
		renderComponent(TrackFiltersEditor, {
			props: {
				value: {
					min_duration_seconds: null,
					max_duration_seconds: null,
					title_indices: null,
					title_indices_exclude: null
				},
				onchange: vi.fn()
			}
		});
		expect(screen.getByTestId('tf-allowlist')).toHaveValue('');
		expect(screen.getByTestId('tf-blocklist')).toHaveValue('');
	});
});
