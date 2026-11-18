import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/testing/render';
import MakemkvKeyField from '../MakemkvKeyField.svelte';
import type { ConfigFieldMeta } from '$lib/types/api.gen';

// Branch pins for MakemkvKeyField, beside MakemkvKeyField.test.ts. No branch
// is left open: every branch of the component is reached below.

const fetchConfigView = vi.fn();
const fetchDrives = vi.fn();
vi.mock('$lib/api/config', () => ({
	fetchConfigView: () => fetchConfigView(),
	HIDDEN_SECRET: '<hidden>'
}));
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

describe('MakemkvKeyField key input', () => {
	it('sets the value as a key is typed', async () => {
		renderComponent(MakemkvKeyField, { props: { field, value: 'T-old' } });
		const input = screen.getByLabelText('Registration key') as HTMLInputElement;
		await fireEvent.input(input, { target: { value: 'T-new' } });
		expect(input.value).toBe('T-new');
	});

	it('shows the key as text on reveal and hides it again', async () => {
		renderComponent(MakemkvKeyField, { props: { field, value: 'T-abc' } });
		const input = screen.getByLabelText('Registration key') as HTMLInputElement;
		expect(input.type).toBe('password');
		await fireEvent.click(screen.getByRole('button', { name: 'Show registration key' }));
		expect(input.type).toBe('text');
		await fireEvent.click(screen.getByRole('button', { name: 'Show registration key' }));
		expect(input.type).toBe('password');
	});

	it('shows a saved key as an empty input with the keep placeholder and the Saved line', () => {
		renderComponent(MakemkvKeyField, { props: { field, value: '<hidden>' } });
		const input = screen.getByLabelText('Registration key') as HTMLInputElement;
		expect(input.value).toBe('');
		expect(input.placeholder).toBe('******** (set, leave blank to keep)');
		expect(screen.getByText('Saved')).toBeInTheDocument();
	});

	it('shows an unsaved key with the T- placeholder and no Saved line', () => {
		renderComponent(MakemkvKeyField, { props: { field, value: 'T-abc' } });
		const input = screen.getByLabelText('Registration key') as HTMLInputElement;
		expect(input.value).toBe('T-abc');
		expect(input.placeholder).toBe('T-...');
		expect(screen.queryByText('Saved')).not.toBeInTheDocument();
	});

	it('shows an empty input when the key is null after choosing the purchased key', async () => {
		renderComponent(MakemkvKeyField, { props: { field, value: null } });
		await fireEvent.click(screen.getByRole('radio', { name: /purchased key/i }));
		expect((screen.getByLabelText('Registration key') as HTMLInputElement).value).toBe('');
	});
});

describe('MakemkvKeyField mode', () => {
	it('opens a saved key on the purchased key option', () => {
		renderComponent(MakemkvKeyField, { props: { field, value: 'T-abc' } });
		expect(screen.getByRole('radio', { name: /purchased key/i })).toBeChecked();
	});

	it('clears a set key and reports onclear when the beta key is chosen', async () => {
		const onclear = vi.fn();
		renderComponent(MakemkvKeyField, { props: { field, value: 'T-abc', onclear } });
		await fireEvent.click(screen.getByRole('radio', { name: /free beta key/i }));
		expect(onclear).toHaveBeenCalledTimes(1);
		await waitFor(() => expect(screen.queryByLabelText('Registration key')).toBeNull());
	});

	it('clears a set key without an onclear handler', async () => {
		renderComponent(MakemkvKeyField, { props: { field, value: 'T-abc' } });
		await fireEvent.click(screen.getByRole('radio', { name: /free beta key/i }));
		await waitFor(() => expect(screen.queryByLabelText('Registration key')).toBeNull());
	});

	it('neither clears nor reports onclear when the beta key is chosen with no key set', async () => {
		const onclear = vi.fn();
		renderComponent(MakemkvKeyField, { props: { field, value: null, onclear } });
		await fireEvent.click(screen.getByRole('radio', { name: /purchased key/i }));
		await fireEvent.click(screen.getByRole('radio', { name: /free beta key/i }));
		expect(onclear).not.toHaveBeenCalled();
	});

	it('does nothing more when the purchased key is chosen with a key set', async () => {
		const onclear = vi.fn();
		renderComponent(MakemkvKeyField, { props: { field, value: 'T-abc', onclear } });
		await fireEvent.click(screen.getByRole('radio', { name: /free beta key/i }));
		await fireEvent.click(screen.getByRole('radio', { name: /purchased key/i }));
		expect(onclear).toHaveBeenCalledTimes(1);
	});
});

describe('MakemkvKeyField status', () => {
	it('reads Valid for a valid key when no drive is reported as checking it', async () => {
		fetchConfigView.mockResolvedValue({ makemkv_key_valid: true, makemkv_key_checked_by_drive_id: null });
		renderComponent(MakemkvKeyField, { props: { field, value: null } });
		expect(await screen.findByText('Valid')).toBeInTheDocument();
	});

	it('reads Valid when the checking drive is not in the list', async () => {
		fetchDrives.mockResolvedValue([drive]);
		fetchConfigView.mockResolvedValue({ makemkv_key_valid: true, makemkv_key_checked_by_drive_id: 'drv_gone' });
		renderComponent(MakemkvKeyField, { props: { field, value: null } });
		expect(await screen.findByText('Valid')).toBeInTheDocument();
	});

	it('shows no message for a rejected key with no reported state', async () => {
		fetchConfigView.mockResolvedValue({ makemkv_key_valid: false });
		renderComponent(MakemkvKeyField, { props: { field, value: null } });
		expect(await screen.findByText('Key not accepted')).toBeInTheDocument();
		expect(screen.getByRole('status')).toHaveTextContent(/^Key not accepted$/);
	});

	it('does not count a virtual drive as enrolled', async () => {
		fetchDrives.mockResolvedValue([{ ...drive, kind: 'virtual' }]);
		renderComponent(MakemkvKeyField, { props: { field, value: null } });
		expect(await screen.findByText('Will be checked when you enroll a drive')).toBeInTheDocument();
	});

	it('does not count an unenrolled drive as enrolled', async () => {
		fetchDrives.mockResolvedValue([{ ...drive, lifecycle: 'discovered' }]);
		renderComponent(MakemkvKeyField, { props: { field, value: null } });
		expect(await screen.findByText('Will be checked when you enroll a drive')).toBeInTheDocument();
	});
});
