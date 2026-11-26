import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent, waitFor } from '$lib/testing/render';
import ConfigSchemaField from '../ConfigSchemaField.svelte';
import type { ConfigFieldMeta } from '$lib/types/api.gen';

// Branch pins for ConfigSchemaField, beside ConfigSchemaField.test.ts. No
// branch of the source is left open. The coverage tool still reports one on
// an enum's `<option value={opt}>`, which is Svelte's, not the component's:
// it compiles the attribute to `(option.__value = opt) ?? ''`, and an option
// is never null, since `enum_values` holds strings.

const fetchConfigView = vi.fn();
const fetchDrives = vi.fn();
vi.mock('$lib/api/config', () => ({
	fetchConfigView: () => fetchConfigView(),
	HIDDEN_SECRET: '<hidden>'
}));
vi.mock('$lib/api/drives', () => ({ fetchDrives: () => fetchDrives() }));

const f = (over: Partial<ConfigFieldMeta>): ConfigFieldMeta => ({
	key: 'k',
	group: 'G',
	tier: 'operator',
	label: 'Label',
	help: 'Help',
	type: 'string',
	editable: true,
	enum_values: null,
	...over
});

beforeEach(() => {
	fetchConfigView.mockResolvedValue({ makemkv_key_valid: null, makemkv_key_checked_by_drive_id: null });
	fetchDrives.mockResolvedValue([]);
});
afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe('ConfigSchemaField widgets', () => {
	it('renders the MakeMKV key card for an editable makemkv_key field', async () => {
		renderComponent(ConfigSchemaField, {
			props: { field: f({ key: 'makemkv_key', label: 'MakeMKV key', widget: 'makemkv_key' }), value: null }
		});
		expect(screen.getByRole('radio', { name: /free beta key/i })).toBeInTheDocument();
		expect(await screen.findByText('Will be checked when you enroll a drive')).toBeInTheDocument();
	});

	it('renders the disc handling card for an editable disc_handling field', async () => {
		renderComponent(ConfigSchemaField, {
			props: {
				field: f({ key: 'disc_handling', label: 'Disc handling', widget: 'disc_handling' }),
				value: null,
				config: {}
			}
		});
		expect(screen.getByRole('radio', { name: /fully automatic/i })).toBeInTheDocument();
		await waitFor(() => expect(fetchDrives).toHaveBeenCalled());
	});

	it('shows a non-editable makemkv_key field as its plain read-only value', () => {
		renderComponent(ConfigSchemaField, {
			props: {
				field: f({ key: 'makemkv_key', label: 'MakeMKV key', widget: 'makemkv_key', editable: false }),
				value: 'T-abc'
			}
		});
		expect(screen.getByText('T-abc')).toBeInTheDocument();
		expect(screen.queryByRole('radio')).not.toBeInTheDocument();
	});

	it('shows a non-editable disc_handling field as its plain read-only value', () => {
		renderComponent(ConfigSchemaField, {
			props: {
				field: f({ key: 'disc_handling', label: 'Disc handling', widget: 'disc_handling', editable: false }),
				value: 'auto'
			}
		});
		expect(screen.getByText('auto')).toBeInTheDocument();
		expect(screen.queryByRole('radio')).not.toBeInTheDocument();
	});
});

describe('ConfigSchemaField read-only values', () => {
	const ranked = (value: unknown, enum_labels: Record<string, string> | null = { a: 'Alpha' }) =>
		renderComponent(ConfigSchemaField, {
			props: { field: f({ type: 'ranked', editable: false, label: 'Sources', enum_labels }), value }
		});

	it('joins a ranked list labels with a comma and shows a value with no label as itself', () => {
		ranked(['a', 'b']);
		expect(screen.getByTestId('setting-k')).toHaveTextContent('Alpha, b');
	});

	it('shows a ranked value as itself when the field has no labels at all', () => {
		ranked(['a', 'b'], null);
		expect(screen.getByTestId('setting-k')).toHaveTextContent('a, b');
	});

	it('shows a dash for an empty ranked list', () => {
		ranked([]);
		expect(screen.getByText('-')).toBeInTheDocument();
	});

	it('shows a dash for a ranked value that is not a list', () => {
		ranked('a');
		expect(screen.getByText('-')).toBeInTheDocument();
	});

	it('shows True for a true read-only bool', () => {
		renderComponent(ConfigSchemaField, {
			props: { field: f({ type: 'bool', editable: false }), value: true }
		});
		expect(screen.getByText('True')).toBeInTheDocument();
	});

	it('shows False for a false read-only bool', () => {
		renderComponent(ConfigSchemaField, {
			props: { field: f({ type: 'bool', editable: false }), value: false }
		});
		expect(screen.getByText('False')).toBeInTheDocument();
	});

	it('shows the value of any other read-only type', () => {
		renderComponent(ConfigSchemaField, {
			props: { field: f({ type: 'int', editable: false }), value: 42 }
		});
		expect(screen.getByText('42')).toBeInTheDocument();
	});

	it('shows a dash for a read-only field with no value', () => {
		renderComponent(ConfigSchemaField, {
			props: { field: f({ type: 'string', editable: false }), value: null }
		});
		expect(screen.getByText('-')).toBeInTheDocument();
	});
});

describe('ConfigSchemaField controls', () => {
	it('shows each enum option by its label, or by itself when it has none', () => {
		renderComponent(ConfigSchemaField, {
			props: {
				field: f({ type: 'enum', label: 'Provider', enum_values: ['tmdb', 'omdb'], enum_labels: { tmdb: 'TMDb' } }),
				value: 'tmdb'
			}
		});
		expect(screen.getByRole('option', { name: 'TMDb' })).toBeInTheDocument();
		expect(screen.getByRole('option', { name: 'omdb' })).toBeInTheDocument();
	});

	it('shows each enum option as itself when the field has no labels', () => {
		renderComponent(ConfigSchemaField, {
			props: { field: f({ type: 'enum', label: 'Provider', enum_values: ['tmdb'], enum_labels: null }), value: 'tmdb' }
		});
		expect(screen.getByRole('option', { name: 'tmdb' })).toBeInTheDocument();
	});

	it('renders an empty select for an enum with no options', () => {
		renderComponent(ConfigSchemaField, {
			props: { field: f({ type: 'enum', label: 'Provider', enum_values: null }), value: null }
		});
		expect(screen.getByRole('combobox', { name: 'Provider' })).toBeInTheDocument();
		expect(screen.queryAllByRole('option')).toHaveLength(0);
	});

	it('gives an int field null when emptied and a number when typed into', async () => {
		renderComponent(ConfigSchemaField, {
			props: { field: f({ type: 'int', label: 'Count' }), value: 5 }
		});
		const input = screen.getByRole('spinbutton', { name: 'Count' }) as HTMLInputElement;
		expect(input.value).toBe('5');
		await fireEvent.input(input, { target: { value: '' } });
		expect(input.value).toBe('');
		await fireEvent.input(input, { target: { value: '12' } });
		expect(input.value).toBe('12');
	});

	it('shows an int field with no value as an empty input', () => {
		renderComponent(ConfigSchemaField, {
			props: { field: f({ type: 'int', label: 'Count' }), value: null }
		});
		expect((screen.getByRole('spinbutton', { name: 'Count' }) as HTMLInputElement).value).toBe('');
	});

	it('gives an editable ranked list with no help no describing id', () => {
		renderComponent(ConfigSchemaField, {
			props: {
				field: f({
					type: 'ranked',
					label: 'Sources',
					help: '',
					enum_values: ['tmdb'],
					enum_labels: { tmdb: 'TMDb' }
				}),
				value: ['tmdb']
			}
		});
		expect(screen.getByRole('list', { name: 'Sources' })).not.toHaveAttribute('aria-describedby');
	});

	it('gives a field with no help no aria-describedby id of its own', () => {
		renderComponent(ConfigSchemaField, {
			props: { field: f({ type: 'string', label: 'Name', help: '' }), value: 'x' }
		});
		expect(screen.getByRole('textbox', { name: 'Name' })).not.toHaveAttribute('aria-describedby');
		expect(screen.getByTestId('setting-k')).not.toHaveTextContent('Help');
	});
});

describe('ConfigSchemaField plain text', () => {
	it('keeps what is typed into it', async () => {
		renderComponent(ConfigSchemaField, {
			props: { field: f({ type: 'string', label: 'Name' }), value: 'old' }
		});
		const input = screen.getByRole('textbox', { name: 'Name' }) as HTMLInputElement;
		expect(input.value).toBe('old');
		await fireEvent.input(input, { target: { value: 'new' } });
		expect(input.value).toBe('new');
	});

	it('shows a null value as an empty text input', () => {
		renderComponent(ConfigSchemaField, {
			props: { field: f({ type: 'string', label: 'Name' }), value: null }
		});
		const input = screen.getByRole('textbox', { name: 'Name' }) as HTMLInputElement;
		expect(input.value).toBe('');
		expect(input.type).toBe('text');
	});
});
