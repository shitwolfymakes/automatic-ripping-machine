import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import JobRawMetadata from '../JobRawMetadata.svelte';

afterEach(cleanup);

const PAIRS: [string, unknown][] = [
	['title', 'Alien'],
	['year', 1979]
];

describe('JobRawMetadata', () => {
	it('is closed by default with no tree shown', () => {
		renderComponent(JobRawMetadata, { pairs: PAIRS });
		const toggle = screen.getByRole('button', { name: 'Raw metadata' });
		expect(toggle).toHaveAttribute('aria-expanded', 'false');
		expect(screen.queryByText('title')).not.toBeInTheDocument();
		expect(screen.queryByText('year')).not.toBeInTheDocument();
	});

	it('shows one tree per pair, by key name, when opened', async () => {
		renderComponent(JobRawMetadata, { pairs: PAIRS });
		const toggle = screen.getByRole('button', { name: 'Raw metadata' });
		await fireEvent.click(toggle);
		expect(toggle).toHaveAttribute('aria-expanded', 'true');
		expect(screen.getByText('title')).toBeInTheDocument();
		expect(screen.getByText('year')).toBeInTheDocument();
	});

	it('hides the trees again when closed', async () => {
		renderComponent(JobRawMetadata, { pairs: PAIRS });
		const toggle = screen.getByRole('button', { name: 'Raw metadata' });
		await fireEvent.click(toggle);
		await fireEvent.click(toggle);
		expect(toggle).toHaveAttribute('aria-expanded', 'false');
		expect(screen.queryByText('title')).not.toBeInTheDocument();
	});
});
