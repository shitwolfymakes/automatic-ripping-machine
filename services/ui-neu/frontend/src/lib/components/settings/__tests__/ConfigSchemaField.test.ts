import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/test-utils';
import ConfigSchemaField from '../ConfigSchemaField.svelte';
import type { ConfigFieldMeta } from '$lib/types/api.gen';

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

afterEach(() => cleanup());

describe('ConfigSchemaField', () => {
	it('renders a bool field as a checkbox', () => {
		renderComponent(ConfigSchemaField, {
			props: { field: f({ key: 'auto_rip_on_insert', type: 'bool', label: 'Auto-rip' }), value: true }
		});
		const cb = screen.getByRole('checkbox', { name: /auto-rip/i });
		expect((cb as HTMLInputElement).checked).toBe(true);
	});

	it('renders an enum field as a select with its options', () => {
		renderComponent(ConfigSchemaField, {
			props: {
				field: f({ key: 'metadata_provider', type: 'enum', label: 'Provider', enum_values: ['tmdb', 'omdb'] }),
				value: 'tmdb'
			}
		});
		const sel = screen.getByRole('combobox', { name: /provider/i });
		expect((sel as HTMLSelectElement).value).toBe('tmdb');
		expect(screen.getByRole('option', { name: 'omdb' })).toBeInTheDocument();
	});

	it('masks a secret field whose value is the <hidden> sentinel', () => {
		renderComponent(ConfigSchemaField, {
			props: { field: f({ key: 'tmdb_api_key', type: 'string', tier: 'secret', label: 'TMDb key' }), value: '<hidden>' }
		});
		const input = screen.getByLabelText(/tmdb key/i) as HTMLInputElement;
		expect(input.type).toBe('password');
		expect(input.value).toBe('');
		expect(input.placeholder).toMatch(/set, leave blank to keep/i);
	});

	it('renders an editable:false field as read-only (no input)', () => {
		renderComponent(ConfigSchemaField, {
			props: {
				field: f({ key: 'RAW_ROOT', type: 'string', tier: 'infra', editable: false, label: 'Raw root' }),
				value: '/raw'
			}
		});
		expect(screen.getByText('/raw')).toBeInTheDocument();
		expect(screen.queryByRole('textbox', { name: /raw root/i })).not.toBeInTheDocument();
	});

	it('shows the label and help text', () => {
		renderComponent(ConfigSchemaField, {
			props: { field: f({ label: 'My Field', help: 'Some guidance' }), value: 'x' }
		});
		expect(screen.getByText('My Field')).toBeInTheDocument();
		expect(screen.getByText('Some guidance')).toBeInTheDocument();
	});

	it('renders an int field as a compact number input that emits numbers', async () => {
		renderComponent(ConfigSchemaField, {
			props: { field: f({ type: 'int', label: 'Match tolerance (seconds)' }), value: 300 }
		});
		const input = screen.getByRole('spinbutton', { name: 'Match tolerance (seconds)' });
		expect(input).toHaveClass('field-control', 'config-schema-field-number');
		await fireEvent.input(input, { target: { value: '120' } });
		expect(input).toHaveValue(120);
	});

	it('shows enum labels while keeping raw values', () => {
		renderComponent(ConfigSchemaField, {
			props: {
				field: f({ type: 'enum', enum_values: ['tmdb', 'omdb'], enum_labels: { tmdb: 'TMDb', omdb: 'OMDb' } }),
				value: 'tmdb'
			}
		});
		const option = screen.getByRole('option', { name: 'TMDb' }) as HTMLOptionElement;
		expect(option.value).toBe('tmdb');
	});

	it('renders a ranked field as a labelled list', () => {
		renderComponent(ConfigSchemaField, {
			props: {
				field: f({
					key: 'episode_sources',
					type: 'ranked',
					label: 'Episode sources',
					enum_values: ['tmdb', 'tvmaze', 'tvdb'],
					enum_labels: { tmdb: 'TMDb', tvmaze: 'TVmaze', tvdb: 'TVDB' }
				}),
				value: ['tmdb']
			}
		});
		expect(screen.getByRole('list', { name: 'Episode sources' })).toBeInTheDocument();
	});

	it('renders a ranked, non-editable field as plain text with no list', () => {
		renderComponent(ConfigSchemaField, {
			props: {
				field: f({
					key: 'episode_sources',
					type: 'ranked',
					label: 'Episode sources',
					editable: false,
					enum_values: ['tmdb', 'tvmaze', 'tvdb'],
					enum_labels: { tmdb: 'TMDb', tvmaze: 'TVmaze', tvdb: 'TVDB' }
				}),
				value: ['tvmaze', 'tmdb']
			}
		});
		expect(screen.getByText('TVmaze, TMDb')).toBeInTheDocument();
		expect(screen.queryByRole('list')).not.toBeInTheDocument();
	});
});
