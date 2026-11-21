import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent, waitFor } from '$lib/test-utils';
import CopyReportButton from '../CopyReportButton.svelte';
import { toasts } from '$lib/stores/toast.svelte';

const report = '## ARM deployment report\n';

function setClipboard(value: unknown) {
	Object.defineProperty(navigator, 'clipboard', { value, configurable: true });
}

describe('CopyReportButton', () => {
	afterEach(() => {
		cleanup();
		toasts.value = [];
	});

	it('copies via clipboard and toasts', async () => {
		const writeText = vi.fn(() => Promise.resolve());
		setClipboard({ writeText });
		renderComponent(CopyReportButton, { props: { getReport: () => Promise.resolve(report) } });
		await fireEvent.click(screen.getByRole('button', { name: 'Copy deployment report' }));
		await waitFor(() => expect(writeText).toHaveBeenCalledWith(report));
		await waitFor(() => expect(toasts.value.some((t) => t.tone === 'success')).toBe(true));
	});

	it('falls back to a textarea dialog without clipboard', async () => {
		setClipboard(undefined);
		renderComponent(CopyReportButton, { props: { getReport: () => Promise.resolve(report) } });
		await fireEvent.click(screen.getByRole('button', { name: 'Copy deployment report' }));
		expect(await screen.findByRole('textbox')).toHaveValue(report);
	});

	it('falls back when the clipboard rejects', async () => {
		setClipboard({ writeText: vi.fn(() => Promise.reject(new Error('denied'))) });
		renderComponent(CopyReportButton, { props: { getReport: () => Promise.resolve(report) } });
		await fireEvent.click(screen.getByRole('button', { name: 'Copy deployment report' }));
		expect(await screen.findByRole('textbox')).toHaveValue(report);
	});

	it('toasts an error when the report cannot be built', async () => {
		renderComponent(CopyReportButton, { props: { getReport: () => Promise.reject(new Error('boom')) } });
		await fireEvent.click(screen.getByRole('button', { name: 'Copy deployment report' }));
		await waitFor(() => expect(toasts.value.some((t) => t.tone === 'error')).toBe(true));
	});
});
