import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
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
			props: { field: f({ key: 'RAW_ROOT', type: 'string', tier: 'infra', editable: false, label: 'Raw root' }), value: '/raw' }
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
});
