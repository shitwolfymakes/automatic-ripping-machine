import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, within } from '$lib/test-utils';
import TranscodeCapabilityStatus from '../TranscodeCapabilityStatus.svelte';

afterEach(cleanup);

describe('TranscodeCapabilityStatus', () => {
	it('reads Transcoding supported, in the ok tone, on a capable deployment', () => {
		renderComponent(TranscodeCapabilityStatus, { props: { capable: true } });
		const status = screen.getByTestId('transcode-capability');
		expect(within(status).getByText('Deployment')).toBeInTheDocument();
		const strip = within(status).getByRole('status');
		expect(strip).toHaveAttribute('data-tone', 'ok');
		expect(strip).toHaveTextContent('Transcoding supported');
	});

	it('reads Transcoding unsupported, in the muted tone, on a ripper-only deployment', () => {
		renderComponent(TranscodeCapabilityStatus, { props: { capable: false } });
		const strip = within(screen.getByTestId('transcode-capability')).getByRole('status');
		expect(strip).toHaveAttribute('data-tone', 'muted');
		expect(strip).toHaveTextContent('Transcoding unsupported');
	});

	it('adds No GPU enabled, CPU encoding enabled, when no GPU is enabled', () => {
		renderComponent(TranscodeCapabilityStatus, { props: { capable: true, gpuEnabled: false } });
		const strips = within(screen.getByTestId('transcode-capability')).getAllByRole('status');
		expect(strips).toHaveLength(2);
		expect(strips[1]).toHaveAttribute('data-tone', 'muted');
		expect(strips[1]).toHaveTextContent('No GPU enabled');
		expect(strips[1]).toHaveTextContent('CPU encoding enabled');
	});

	it('adds nothing while the GPU list is unknown or when a GPU is enabled', () => {
		renderComponent(TranscodeCapabilityStatus, { props: { capable: true } });
		expect(within(screen.getByTestId('transcode-capability')).getAllByRole('status')).toHaveLength(1);
		cleanup();
		renderComponent(TranscodeCapabilityStatus, { props: { capable: true, gpuEnabled: true } });
		expect(within(screen.getByTestId('transcode-capability')).getAllByRole('status')).toHaveLength(1);
	});
});
