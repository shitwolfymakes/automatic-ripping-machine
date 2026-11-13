import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import FeedbackAlert from '../FeedbackAlert.svelte';

afterEach(cleanup);

describe('FeedbackAlert', () => {
	it('draws nothing without feedback', () => {
		const { container } = renderComponent(FeedbackAlert, { props: { feedback: null } });
		expect(container.querySelector('.alert')).toBeNull();
	});

	it('shows a success message in the success style when it appears', async () => {
		const { rerender } = renderComponent(FeedbackAlert, { props: { feedback: null } });
		await rerender({ feedback: { type: 'success', message: 'Saved' } });
		const alert = screen.getByText('Saved');
		expect(alert.classList.contains('alert-success')).toBe(true);
		expect(alert.classList.contains('alert-danger')).toBe(false);
	});

	it('shows an error message in the danger style when it appears', async () => {
		const { rerender } = renderComponent(FeedbackAlert, { props: { feedback: null } });
		await rerender({ feedback: { type: 'error', message: 'Failed' } });
		const alert = screen.getByText('Failed');
		expect(alert.classList.contains('alert-danger')).toBe(true);
		expect(alert.classList.contains('alert-success')).toBe(false);
	});
});
