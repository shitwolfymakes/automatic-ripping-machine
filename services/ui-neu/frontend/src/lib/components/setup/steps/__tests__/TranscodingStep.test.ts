import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor } from '$lib/testing/render';
import type { SetupView } from '$lib/types/api.gen';
import { setTranscoderEnabled } from '$lib/stores/config';

// Tests for TranscodingStep. No branch is left open.

// GpusCard and SetupConfigFields are stand-ins: a Svelte component is a
// function of (anchor, props), and what it returns is what `bind:this` holds.
const gpusProps = vi.hoisted(() => ({ current: null as { location: { label: string } | null } | null }));
const fieldsState = vi.hoisted(() => ({ save: null as (() => Promise<boolean>) | null }));

vi.mock('$lib/components/shared/GpusCard.svelte', () => ({
	default: (_anchor: unknown, props: { location: { label: string } | null }) => {
		gpusProps.current = props;
	}
}));
vi.mock('../../SetupConfigFields.svelte', () => ({
	default: () => (fieldsState.save ? { save: fieldsState.save } : undefined)
}));

const fetchSystemDiagnostics = vi.fn();
vi.mock('$lib/api/system', () => ({ fetchSystemDiagnostics: () => fetchSystemDiagnostics() }));

import TranscodingStep from '../TranscodingStep.svelte';

const view = { completed_at: null, progress: {}, current_step: 'transcoding' } as unknown as SetupView;
type Step = { commit(): Promise<string | false> };

const withTranscoder = (check: Record<string, unknown> | null) =>
	fetchSystemDiagnostics.mockResolvedValue({ status: 'ok', paths: [], checks: check ? [check] : [] });
const locationAfterLoad = async () => {
	await waitFor(() => expect(fetchSystemDiagnostics).toHaveBeenCalled());
	// the location is set after the awaited call resolves
	await Promise.resolve();
	await Promise.resolve();
	return gpusProps.current?.location;
};

beforeEach(() => {
	setTranscoderEnabled(true);
	gpusProps.current = null;
	fieldsState.save = async () => true;
});
afterEach(() => {
	cleanup();
	fetchSystemDiagnostics.mockReset();
});

describe('TranscodingStep with transcoding off', () => {
	beforeEach(() => setTranscoderEnabled(false));

	it('shows the ripper-only note and does not look up the transcoder', () => {
		renderComponent(TranscodingStep, { props: { view } });
		expect(screen.getByTestId('transcoding-ripper-only')).toHaveTextContent(
			'This install only rips; encoding happens elsewhere or not at all.'
		);
		expect(fetchSystemDiagnostics).not.toHaveBeenCalled();
		expect(gpusProps.current).toBeNull();
	});

	it('commits done without saving', async () => {
		const save = vi.fn(async () => true);
		fieldsState.save = save;
		const { component } = renderComponent(TranscodingStep, { props: { view } });
		expect(await (component as unknown as Step).commit()).toBe('done');
		expect(save).not.toHaveBeenCalled();
	});
});

describe('TranscodingStep with transcoding on', () => {
	it('tells the GPUs card "This server" for a local transcoder', async () => {
		withTranscoder({ name: 'transcoder', status: 'ok', location: 'local' });
		renderComponent(TranscodingStep, { props: { view } });
		await waitFor(() => expect(gpusProps.current?.location).toEqual({ label: 'This server' }));
	});

	it('tells the GPUs card "Remote host <name>" for a remote transcoder', async () => {
		withTranscoder({ name: 'transcoder', status: 'ok', location: 'remote', remote_host: 'enc1' });
		renderComponent(TranscodingStep, { props: { view } });
		await waitFor(() => expect(gpusProps.current?.location).toEqual({ label: 'Remote host enc1' }));
	});

	it('tells the GPUs card just "Remote host" for a remote transcoder with no name', async () => {
		withTranscoder({ name: 'transcoder', status: 'ok', location: 'remote' });
		renderComponent(TranscodingStep, { props: { view } });
		await waitFor(() => expect(gpusProps.current?.location).toEqual({ label: 'Remote host' }));
	});

	it('gives the GPUs card no location for a transcoder with another location', async () => {
		withTranscoder({ name: 'transcoder', status: 'ok', location: 'none' });
		renderComponent(TranscodingStep, { props: { view } });
		expect(await locationAfterLoad()).toBeNull();
	});

	it('gives the GPUs card no location for a transcoder with no location', async () => {
		withTranscoder({ name: 'transcoder', status: 'ok' });
		renderComponent(TranscodingStep, { props: { view } });
		expect(await locationAfterLoad()).toBeNull();
	});

	it('gives the GPUs card no location when there is no transcoder check', async () => {
		withTranscoder(null);
		renderComponent(TranscodingStep, { props: { view } });
		expect(await locationAfterLoad()).toBeNull();
	});

	it('gives the GPUs card no location when the diagnostics call fails', async () => {
		fetchSystemDiagnostics.mockRejectedValue(new Error('503'));
		renderComponent(TranscodingStep, { props: { view } });
		expect(await locationAfterLoad()).toBeNull();
	});

	it('saves the fields and commits done', async () => {
		withTranscoder(null);
		const save = vi.fn(async () => true);
		fieldsState.save = save;
		const { component } = renderComponent(TranscodingStep, { props: { view } });
		expect(await (component as unknown as Step).commit()).toBe('done');
		expect(save).toHaveBeenCalledTimes(1);
	});

	it('commits false when the save fails', async () => {
		withTranscoder(null);
		fieldsState.save = async () => false;
		const { component } = renderComponent(TranscodingStep, { props: { view } });
		expect(await (component as unknown as Step).commit()).toBe(false);
	});

	it('commits false when the fields are not there', async () => {
		withTranscoder(null);
		const { component } = renderComponent(TranscodingStep, { props: { view } });
		// Unmounting clears `bind:this`, which leaves the step with no fields.
		cleanup();
		expect(await (component as unknown as Step).commit()).toBe(false);
	});
});
