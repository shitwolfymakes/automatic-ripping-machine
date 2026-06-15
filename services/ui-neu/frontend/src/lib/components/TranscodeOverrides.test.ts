import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, waitFor, cleanup } from '$lib/test-utils';
import { fireEvent } from '@testing-library/svelte';
import TranscodeOverrides from './TranscodeOverrides.svelte';
import { createJob } from './__fixtures__/job';

vi.mock('$lib/api/settings', () => ({
    fetchTranscoderScheme: vi.fn().mockResolvedValue({
        slug: 'software', name: 'Software (CPU)',
        supported_encoders: [{ slug: 'x265', name: 'x265', tuning_presets: [] }],
        supported_audio_encoders: ['copy', 'aac'],
        supported_subtitle_modes: ['all'],
        advanced_fields: {}
    }),
    fetchTranscoderPresets: vi.fn().mockResolvedValue({
        presets: [{
            slug: 'software_balanced', name: 'Balanced', scheme: 'software',
            description: '', builtin: true,
            shared: {}, tiers: { dvd: {}, bluray: {}, uhd: {} }
        }]
    })
}));

const updateMock = vi.fn().mockResolvedValue({ id: 'job_1' });
vi.mock('$lib/api/jobs', () => ({
    updateJobTranscodeConfig: (...args: unknown[]) => updateMock(...args)
}));

beforeEach(() => updateMock.mockClear());
afterEach(() => cleanup());

describe('TranscodeOverrides', () => {
    it('renders PresetEditor and submits new-shape overrides on save', async () => {
        const { container } = renderComponent(TranscodeOverrides, {
            props: { job: createJob({ id: 'job_1' }) }
        });
        await waitFor(() => screen.getByText(/Software \(CPU\)/));
        const qualityInput = container.querySelector('input[data-testid="tier-bluray-quality"]') as HTMLInputElement;
        await fireEvent.input(qualityInput, { target: { value: '18' } });
        await fireEvent.click(screen.getByRole('button', { name: /Save changes/i }));
        await waitFor(() => expect(updateMock).toHaveBeenCalled());
        expect(updateMock).toHaveBeenCalledWith('job_1', expect.objectContaining({
            overrides: expect.objectContaining({ tiers: expect.objectContaining({ bluray: { video_quality: 18 } }) })
        }));
    });

    it('does not show "Save as new preset" (scope=job)', async () => {
        renderComponent(TranscodeOverrides, { props: { job: createJob() } });
        await waitFor(() => screen.getByText(/Software \(CPU\)/));
        expect(screen.queryByText(/Save as new preset/i)).toBeNull();
    });

    it('defaults to empty preset state', async () => {
        renderComponent(TranscodeOverrides, { props: { job: createJob({ id: 'job_2' }) } });
        await waitFor(() => screen.getByText(/Software \(CPU\)/));
    });

    it('shows offline state when transcoder is unreachable', async () => {
        const settingsApi = await import('$lib/api/settings');
        vi.mocked(settingsApi.fetchTranscoderScheme).mockResolvedValueOnce(null);
        vi.mocked(settingsApi.fetchTranscoderPresets).mockResolvedValueOnce(null);
        renderComponent(TranscodeOverrides, { props: { job: createJob() } });
        await waitFor(() => expect(screen.queryByText(/Software \(CPU\)/)).toBeNull());
    });
});
