import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/testing/render';
import TranscodingSettings from '../TranscodingSettings.svelte';
import { saveArmConfig } from '$lib/api/settings';
import { setTranscoderEnabled } from '$lib/stores/config';
import type { SettingsGroup } from '$lib/types/api.gen';

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

const GROUP: SettingsGroup = {
	name: 'Transcoding',
	fields: [
		{
			key: 'transcode_enabled',
			group: 'Transcoding',
			tier: 'operator',
			label: 'Enable transcoding',
			help: '',
			type: 'bool',
			editable: true,
			enum_values: null
		},
		{
			key: 'auto_transcode_on_idle',
			group: 'Transcoding',
			tier: 'operator',
			label: 'Auto-transcode on idle',
			help: '',
			type: 'bool',
			editable: true,
			enum_values: null
		}
	]
};

const CONFIG = { transcode_enabled: true, auto_transcode_on_idle: false };

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
	it('renders the schema form and the GPU card on a capable deployment with a group', async () => {
		setTranscoderEnabled(true);
		render(GROUP);
		expect(await screen.findByText('Auto-transcode on idle')).toBeInTheDocument();
		expect(await screen.findByTestId('gpus-card')).toBeInTheDocument();
		expect(screen.queryByText(HINT)).toBeNull();
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
		expect(screen.queryByText('Auto-transcode on idle')).toBeNull();
	});

	it('calls onsaved with the saved values when the form saves', async () => {
		setTranscoderEnabled(true);
		const onsaved = render(GROUP);
		await fireEvent.click(await screen.findByRole('checkbox', { name: 'Auto-transcode on idle' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		await waitFor(() => expect(onsaved).toHaveBeenCalledWith({ auto_transcode_on_idle: true }));
		expect(saveArmConfig).toHaveBeenCalledWith({ auto_transcode_on_idle: true });
	});
});
