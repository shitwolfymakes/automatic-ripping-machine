import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent, waitFor } from '$lib/test-utils';
import CrcLookup from './CrcLookup.svelte';
import { createJob } from './__fixtures__/job';

vi.mock('$lib/api/jobs', () => ({
	updateJobTitle: vi.fn(() => Promise.resolve())
}));

import { updateJobTitle } from '$lib/api/jobs';
const mockUpdateJobTitle = vi.mocked(updateJobTitle);

describe('CrcLookup', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	describe('rendering', () => {
		it('shows CRC hash when present', () => {
			renderComponent(CrcLookup, {
				props: { job: createJob(), crcId: 'abc123def456' }
			});
			expect(screen.getByText('abc123def456')).toBeInTheDocument();
		});

		it('shows the manual poster URL form', () => {
			renderComponent(CrcLookup, {
				props: { job: createJob(), crcId: 'abc123' }
			});
			expect(screen.getByText('Manual poster URL')).toBeInTheDocument();
			expect(screen.getByText('Apply to Job')).toBeInTheDocument();
		});
	});

	describe('coming-soon controls', () => {
		it('renders the CRC lookup control disabled (coming soon)', () => {
			renderComponent(CrcLookup, {
				props: { job: createJob(), crcId: 'abc123' }
			});
			const lookupBtn = screen.getByRole('button', { name: 'Look up' });
			expect(lookupBtn).toBeDisabled();
		});

		it('renders the CRC submit control disabled (coming soon)', () => {
			renderComponent(CrcLookup, {
				props: { job: createJob(), crcId: 'abc123' }
			});
			const submitBtn = screen.getByRole('button', { name: 'Submit to CRC Database' });
			expect(submitBtn).toBeDisabled();
		});
	});

	describe('apply (live)', () => {
		it('applies the manual poster URL via updateJobTitle', async () => {
			renderComponent(CrcLookup, {
				props: { job: createJob({ id: 'job-1' }), crcId: 'abc123' }
			});
			const input = screen.getByPlaceholderText('https://...');
			await fireEvent.input(input, { target: { value: 'https://example.com/poster.jpg' } });
			await fireEvent.click(screen.getByRole('button', { name: 'Apply to Job' }));
			await waitFor(() => {
				expect(mockUpdateJobTitle).toHaveBeenCalledWith('job-1', {
					poster_url_manual: 'https://example.com/poster.jpg'
				});
				expect(screen.getByText('Job updated')).toBeInTheDocument();
			});
		});
	});
});
