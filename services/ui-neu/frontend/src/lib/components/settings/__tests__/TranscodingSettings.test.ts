import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import TranscodingSettings from '../TranscodingSettings.svelte';
import { saveArmConfig } from '$lib/api/settings';
import { setTranscoderEnabled } from '$lib/stores/config';
import type { GpuView, SettingsGroup } from '$lib/types/api.gen';
import { fetchGpus } from '$lib/api/gpus';

vi.mock('$lib/api/settings', () => ({
	fetchSettings: vi.fn(),
	saveArmConfig: vi.fn(() => Promise.resolve({ success: true }))
}));

vi.mock('$lib/api/gpus', () => ({
	fetchGpus: vi.fn(() => Promise.resolve([])),
	updateGpu: vi.fn(),
	deleteGpu: vi.fn()
}));

const HINT = 'This deployment is ripper-only; transcoding cannot be enabled here.';

const field = (key: string, label: string, type: string, editable = true) => ({
	key,
	group: 'Transcoding',
	tier: editable ? 'operator' : 'infra',
	label,
	help: '',
	type,
	editable,
	enum_values: null
});

const GROUP = {
	name: 'Transcoding',
	fields: [
		field('transcode_enabled', 'Enable transcoding', 'bool'),
		field('transcode_capable', 'Transcode capable', 'bool', false),
		field('max_parallel_transcodes', 'Max parallel transcodes', 'int')
	]
} as SettingsGroup;

const CONFIG = { transcode_enabled: true, transcode_capable: true, max_parallel_transcodes: 1 };

function render(group: SettingsGroup | undefined, onsaved = vi.fn()) {
	renderComponent(TranscodingSettings, { props: { group, config: CONFIG, onsaved } });
	return onsaved;
}

afterEach(() => {
	cleanup();
	setTranscoderEnabled(false);
	vi.clearAllMocks();
});

describe('TranscodingSettings', () => {
	it('opens with the supported pill, then the toggle, with the GPU card after the fields', async () => {
		setTranscoderEnabled(true);
		render(GROUP);
		const pill = await screen.findByTestId('transcode-capability');
		const toggle = await screen.findByRole('checkbox', { name: 'Enable transcoding' });
		const gpus = await screen.findByTestId('gpus-card');
		const limit = screen.getByText('Max parallel transcodes');
		expect(pill).toHaveTextContent('Transcoding supported');
		expect(pill.compareDocumentPosition(toggle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
		expect(limit.compareDocumentPosition(gpus) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
		expect(screen.queryByText('Transcode capable')).toBeNull();
		expect(screen.queryByText(HINT)).toBeNull();
	});

	it('shows No GPU enabled under the supported status when the GPU list has none enabled', async () => {
		setTranscoderEnabled(true);
		render(GROUP);
		const status = await screen.findByTestId('transcode-capability');
		await waitFor(() => expect(status).toHaveTextContent('No GPU enabled'));
		expect(status).toHaveTextContent('CPU encoding enabled');
	});

	it('shows no CPU line once the GPU list has an enabled GPU', async () => {
		vi.mocked(fetchGpus).mockResolvedValueOnce([
			{ id: 'gpu_1', vendor: 'qsv', device_path: '/dev/dri/renderD128', enabled: true } as GpuView
		]);
		setTranscoderEnabled(true);
		render(GROUP);
		await screen.findByTestId('gpu-row-gpu_1');
		expect(screen.getByTestId('transcode-capability')).not.toHaveTextContent('No GPU enabled');
	});

	it('shows the locked toggle on a capable deployment with no group', () => {
		setTranscoderEnabled(true);
		render(undefined);
		expect(screen.getByTestId('setting-transcode_enabled')).toBeInTheDocument();
		expect(screen.getByText(HINT)).toBeInTheDocument();
		expect(screen.queryByTestId('gpus-card')).toBeNull();
	});

	it('shows the locked toggle, off and disabled, with the hint on a ripper-only deployment', () => {
		setTranscoderEnabled(false);
		render(GROUP);
		const toggle = screen.getByRole('switch', { name: 'Enable transcoding' });
		expect(toggle).toBeDisabled();
		expect(toggle).toHaveAttribute('aria-checked', 'false');
		expect(screen.getByText(HINT)).toBeInTheDocument();
		expect(screen.queryByTestId('gpus-card')).toBeNull();
		const pill = screen.getByTestId('transcode-capability');
		expect(pill).toHaveTextContent('Transcoding unsupported');
		expect(pill.compareDocumentPosition(toggle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
	});

	it('calls onsaved with the saved values when the form saves', async () => {
		setTranscoderEnabled(true);
		const onsaved = render(GROUP);
		await fireEvent.click(await screen.findByRole('checkbox', { name: 'Enable transcoding' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(onsaved).toHaveBeenCalledWith({ transcode_enabled: false }));
		expect(saveArmConfig).toHaveBeenCalledWith({ transcode_enabled: false });
	});
});
