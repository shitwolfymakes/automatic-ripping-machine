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
});
