import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, within, cleanup } from '$lib/test-utils';
import { createRawSnippet } from 'svelte';
import HealthCheckRow from '../HealthCheckRow.svelte';

function renderRow(status = 'ok') {
	renderComponent(HealthCheckRow, {
		props: {
			testid: 'row-under-test',
			status,
			label: 'Database',
			children: createRawSnippet(() => ({ render: () => '<span>Connected in 3 ms</span>' }))
		}
	});
	return screen.getByTestId('row-under-test');
}

describe('HealthCheckRow', () => {
	afterEach(() => cleanup());

	it('carries the test id and status the caller passes in', () => {
		const row = renderRow('warning');
		expect(row).toHaveAttribute('data-status', 'warning');
	});

	it('gives the status dot the same status as the row', () => {
		const row = renderRow('error');
		// The dot is decorative, with no role or text to find it by.
		expect(row.querySelector('span[data-status]')).toHaveAttribute('data-status', 'error');
	});

	it('shows the label', () => {
		const row = renderRow();
		expect(within(row).getByText('Database')).toBeInTheDocument();
	});

	it('renders the detail the caller passes in', () => {
		const row = renderRow();
		expect(within(row).getByText('Connected in 3 ms')).toBeInTheDocument();
	});
});
