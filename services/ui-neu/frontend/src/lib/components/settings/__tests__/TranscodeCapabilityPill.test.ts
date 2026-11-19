import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import TranscodeCapabilityPill from '../TranscodeCapabilityPill.svelte';

afterEach(cleanup);

describe('TranscodeCapabilityPill', () => {
	it('says transcoding is supported, in the success tone, on a capable deployment', () => {
		renderComponent(TranscodeCapabilityPill, { props: { capable: true } });
		const pill = screen.getByTestId('transcode-capability');
		expect(pill).toHaveTextContent('Transcoding supported');
		expect(pill).toHaveClass('badge', 'badge-success');
	});

	it('says transcoding is unsupported, in the plain tone, on a ripper-only deployment', () => {
		renderComponent(TranscodeCapabilityPill, { props: { capable: false } });
		const pill = screen.getByTestId('transcode-capability');
		expect(pill).toHaveTextContent('Transcoding unsupported');
		expect(pill).toHaveClass('badge');
		expect(pill).not.toHaveClass('badge-success');
	});
});
