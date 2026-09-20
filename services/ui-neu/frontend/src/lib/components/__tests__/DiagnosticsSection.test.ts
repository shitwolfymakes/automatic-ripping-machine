import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor } from '$lib/test-utils';
import DiagnosticsSection from '../DiagnosticsSection.svelte';
import { fetchDiagnostics } from '$lib/api/diagnostics';
import type { DiagnosticsResponse } from '$lib/types/api.gen';

vi.mock('$lib/api/diagnostics', () => ({
	fetchDiagnostics: vi.fn()
}));

const fetchMock = vi.mocked(fetchDiagnostics);

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe('DiagnosticsSection', () => {
	it('renders a row per service with name + log-level badge', async () => {
		fetchMock.mockResolvedValue({
			services: [
				{ name: 'arm-backend', log_level: 'INFO' },
				{ name: 'arm-ripper', log_level: 'DEBUG' }
			]
		} as DiagnosticsResponse);
		renderComponent(DiagnosticsSection);

		await waitFor(() => expect(screen.getByText('arm-backend')).toBeInTheDocument());
		expect(screen.getByText('arm-ripper')).toBeInTheDocument();
		expect(screen.getByTestId('diag-level-arm-backend')).toHaveTextContent('INFO');
		expect(screen.getByTestId('diag-level-arm-ripper')).toHaveTextContent('DEBUG');
	});

	it('shows the ARM_LOG_LEVEL note', async () => {
		fetchMock.mockResolvedValue({ services: [{ name: 'arm-backend', log_level: 'INFO' }] } as DiagnosticsResponse);
		renderComponent(DiagnosticsSection);
		await waitFor(() => expect(screen.getByText('arm-backend')).toBeInTheDocument());
		expect(screen.getByText(/ARM_LOG_LEVEL/)).toBeInTheDocument();
	});

	it('shows a loading placeholder before the fetch resolves', () => {
		fetchMock.mockReturnValue(new Promise(() => {})); // never resolves
		renderComponent(DiagnosticsSection);
		expect(screen.getByText(/Loading diagnostics/i)).toBeInTheDocument();
	});

	it('surfaces a fetch error inline', async () => {
		fetchMock.mockRejectedValue(new Error('diag boom'));
		renderComponent(DiagnosticsSection);
		await waitFor(() => expect(screen.getByTestId('diagnostics-error')).toHaveTextContent('diag boom'));
	});

	it('shows an empty state when there are no services', async () => {
		fetchMock.mockResolvedValue({ services: [] } as DiagnosticsResponse);
		renderComponent(DiagnosticsSection);
		await waitFor(() => expect(screen.getByText(/No services reported/i)).toBeInTheDocument());
	});
});
