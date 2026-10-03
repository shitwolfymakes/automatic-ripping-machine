import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import CopyBlock from '../CopyBlock.svelte';

describe('CopyBlock', () => {
	afterEach(() => cleanup());

	it('copies the text and says so', async () => {
		const writeText = vi.fn(() => Promise.resolve());
		Object.assign(navigator, { clipboard: { writeText } });
		renderComponent(CopyBlock, { props: { text: 'sudo chown -R 1000:1000 /srv/arm/media' } });
		expect(screen.getByText('sudo chown -R 1000:1000 /srv/arm/media')).toHaveClass('mono');
		await fireEvent.click(screen.getByRole('button'));
		expect(writeText).toHaveBeenCalledWith('sudo chown -R 1000:1000 /srv/arm/media');
		await waitFor(() => expect(screen.getByText('Copied')).toBeInTheDocument());
	});

	it('falls back to selecting the text when the clipboard is unavailable', async () => {
		Object.assign(navigator, { clipboard: { writeText: vi.fn(() => Promise.reject(new Error('denied'))) } });
		renderComponent(CopyBlock, { props: { text: 'ARM_HOST_ISO_LIBRARY_PATH=/isos' } });
		await fireEvent.click(screen.getByRole('button'));
		await waitFor(() => expect(screen.getByText('Press Ctrl+C')).toBeInTheDocument());
	});
});
