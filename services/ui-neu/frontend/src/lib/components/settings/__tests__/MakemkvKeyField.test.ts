import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import MakemkvKeyField from '../MakemkvKeyField.svelte';
import type { ConfigFieldMeta } from '$lib/types/api.gen';

const fetchConfigView = vi.fn();
const fetchDrives = vi.fn();
vi.mock('$lib/api/config', () => ({ fetchConfigView: () => fetchConfigView() }));
vi.mock('$lib/api/drives', () => ({ fetchDrives: () => fetchDrives() }));

const field: ConfigFieldMeta = {
	key: 'makemkv_key',
	group: 'Metadata',
	tier: 'secret',
	label: 'MakeMKV key',
	help: '',
	type: 'string',
	editable: true,
	widget: 'makemkv_key'
};
const drive = {
	id: 'drv_1',
	lifecycle: 'enrolled',
	kind: 'optical',
	display_name: 'Living room',
	vendor: 'LG',
	model: 'WH16NS60',
	device_path: '/dev/sr0'
};

beforeEach(() => {
	fetchConfigView.mockResolvedValue({ makemkv_key_valid: null, makemkv_key_checked_by_drive_id: null });
	fetchDrives.mockResolvedValue([]);
});
afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe('MakemkvKeyField', () => {
	it('defaults to the beta key and says a drive will check it', async () => {
		renderComponent(MakemkvKeyField, { props: { field, value: null } });
		expect(screen.getByRole('radio', { name: /free beta key/i })).toBeChecked();
		expect(await screen.findByText('Will be checked when you enroll a drive')).toBeInTheDocument();
	});

	it('waits for an enrolled drive to report', async () => {
		fetchDrives.mockResolvedValue([drive]);
		renderComponent(MakemkvKeyField, { props: { field, value: null } });
		expect(await screen.findByText('Waiting for a drive to check the key...')).toBeInTheDocument();
	});

	it('names the drive that verified the key', async () => {
		fetchDrives.mockResolvedValue([drive]);
		fetchConfigView.mockResolvedValue({ makemkv_key_valid: true, makemkv_key_checked_by_drive_id: 'drv_1' });
		renderComponent(MakemkvKeyField, { props: { field, value: null } });
		expect(await screen.findByText('Valid, checked by Living room')).toBeInTheDocument();
	});

	it('shows a rejected key with the reported state', async () => {
		fetchConfigView.mockResolvedValue({ makemkv_key_valid: false, makemkv_key_state: 'unregistered_or_expired' });
		renderComponent(MakemkvKeyField, { props: { field, value: '<hidden>' } });
		expect(await screen.findByText('Key not accepted')).toBeInTheDocument();
		expect(screen.getByText('unregistered_or_expired')).toHaveClass('mono');
		expect(screen.getByRole('radio', { name: /purchased key/i })).toBeChecked();
	});

	it('switching back to the beta key clears a saved key', async () => {
		const onclear = vi.fn();
		renderComponent(MakemkvKeyField, { props: { field, value: '<hidden>', onclear } });
		await fireEvent.click(screen.getByRole('radio', { name: /free beta key/i }));
		expect(onclear).toHaveBeenCalled();
		await waitFor(() => expect(screen.queryByLabelText('Registration key')).toBeNull());
	});
});
