import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import DiscHandlingField from '../DiscHandlingField.svelte';

const fetchDrives = vi.fn(() => Promise.resolve([] as unknown[]));
vi.mock('$lib/api/drives', () => ({ fetchDrives: () => fetchDrives() }));

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe('DiscHandlingField', () => {
	it('maps the three options onto auto_rip_on_insert + hold_for_review', async () => {
		const values: Record<string, unknown> = { auto_rip_on_insert: true, hold_for_review: false };
		renderComponent(DiscHandlingField, { props: { values, context: { manual_wait_seconds: 45 } } });
		expect(screen.getByRole('radio', { name: /fully automatic/i })).toBeChecked();
		expect(screen.getByText(/waits 45 seconds/i)).toBeInTheDocument();
		expect(screen.getByText('Suggested')).toBeInTheDocument();

		await fireEvent.click(screen.getByRole('radio', { name: /review first/i }));
		expect(values).toMatchObject({ auto_rip_on_insert: true, hold_for_review: true });

		await fireEvent.click(screen.getByRole('radio', { name: /manual/i }));
		expect(values.auto_rip_on_insert).toBe(false);
		expect(values.hold_for_review).toBe(true); // Manual leaves the review setting alone
	});

	it('reads the current choice', () => {
		renderComponent(DiscHandlingField, { props: { values: { auto_rip_on_insert: false, hold_for_review: false } } });
		expect(screen.getByRole('radio', { name: /manual/i })).toBeChecked();
	});

	it('notes drives with their own mode', async () => {
		fetchDrives.mockResolvedValueOnce([
			{ id: 'a', lifecycle: 'enrolled', drive_mode: 'manual' },
			{ id: 'b', lifecycle: 'enrolled', drive_mode: null },
			{ id: 'c', lifecycle: 'detected', drive_mode: 'auto' }
		]);
		renderComponent(DiscHandlingField, { props: { values: { auto_rip_on_insert: true } } });
		await waitFor(() =>
			expect(screen.getByTestId('disc-handling-overrides')).toHaveTextContent(
				"1 drive has its own setting and won't change."
			)
		);
	});
});
