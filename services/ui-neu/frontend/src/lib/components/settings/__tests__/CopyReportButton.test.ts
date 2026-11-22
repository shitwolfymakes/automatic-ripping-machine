import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent, waitFor } from '$lib/testing/render';
import CopyReportButton from '../CopyReportButton.svelte';
import { toasts } from '$lib/stores/toast.svelte';

const report = '## ARM deployment report\n';

function setClipboard(value: unknown) {
	Object.defineProperty(navigator, 'clipboard', { value, configurable: true });
}

const originalClipboard = Object.getOwnPropertyDescriptor(navigator, 'clipboard');

describe('CopyReportButton', () => {
	afterEach(() => {
		if (originalClipboard) Object.defineProperty(navigator, 'clipboard', originalClipboard);
		else delete (navigator as unknown as Record<string, unknown>).clipboard;
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

	async function openFallback() {
		setClipboard(undefined);
		renderComponent(CopyReportButton, { props: { getReport: () => Promise.resolve(report) } });
		await fireEvent.click(screen.getByRole('button', { name: 'Copy deployment report' }));
		await screen.findByRole('textbox');
	}

	it('the fallback is a dialog', async () => {
		await openFallback();
		expect(screen.getByRole('dialog')).toBeInTheDocument();
	});

	it('Escape closes the fallback and returns focus to the button', async () => {
		await openFallback();
		await fireEvent.keyDown(window, { key: 'Escape' });
		expect(screen.queryByRole('dialog')).toBeNull();
		expect(screen.getByRole('button', { name: 'Copy deployment report' })).toHaveFocus();
	});

	it('the Close button closes the fallback', async () => {
		await openFallback();
		await fireEvent.click(screen.getByRole('button', { name: 'Close' }));
		expect(screen.queryByRole('dialog')).toBeNull();
	});
});
