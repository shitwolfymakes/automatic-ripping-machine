import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, within } from '$lib/test-utils';
import JobFingerprints from '../JobFingerprints.svelte';

afterEach(cleanup);

const FINGERPRINTS = [
	{ algo: 'crc64', value: 'ABCDEF0123456789' },
	{ algo: 'sha1', value: 'deadbeefcafe' }
];

describe('JobFingerprints', () => {
	it('shows the section heading and column headers', () => {
		renderComponent(JobFingerprints, { fingerprints: FINGERPRINTS });
		expect(screen.getByRole('heading', { name: 'Disc fingerprints' })).toBeInTheDocument();
		expect(screen.getByText('Algorithm')).toBeInTheDocument();
		expect(screen.getByText('Value')).toBeInTheDocument();
	});

	it('renders one row per fingerprint with its algorithm and value', () => {
		renderComponent(JobFingerprints, { fingerprints: FINGERPRINTS });
		const rows = screen.getAllByRole('row').slice(1);
		expect(rows).toHaveLength(2);
		expect(within(rows[0]).getByText('crc64')).toBeInTheDocument();
		expect(within(rows[0]).getByText('ABCDEF0123456789')).toBeInTheDocument();
		expect(within(rows[1]).getByText('sha1')).toBeInTheDocument();
		expect(within(rows[1]).getByText('deadbeefcafe')).toBeInTheDocument();
	});

	it('puts the full value in the value cell title attribute', () => {
		renderComponent(JobFingerprints, { fingerprints: FINGERPRINTS });
		expect(screen.getByText('deadbeefcafe')).toHaveAttribute('title', 'deadbeefcafe');
	});
});
