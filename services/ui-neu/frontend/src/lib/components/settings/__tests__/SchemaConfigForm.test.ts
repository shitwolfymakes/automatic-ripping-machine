import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import SchemaConfigForm from '../SchemaConfigForm.svelte';
import type { SettingsGroup } from '$lib/types/api.gen';

const saveArmConfig = vi.fn((_config: Record<string, unknown>) => Promise.resolve({ success: true }));
vi.mock('$lib/api/settings', () => ({ saveArmConfig: (config: Record<string, unknown>) => saveArmConfig(config) }));

const GROUP: SettingsGroup = {
  name: 'Metadata',
  fields: [
    { key: 'metadata_provider', group: 'Metadata', tier: 'operator', label: 'Provider', help: '', type: 'enum', editable: true, enum_values: ['tmdb', 'omdb'] },
    { key: 'tmdb_api_key', group: 'Metadata', tier: 'secret', label: 'TMDb key', help: '', type: 'string', editable: true, enum_values: null },
  ],
};
const CONFIG = { metadata_provider: 'tmdb', tmdb_api_key: '<hidden>' };

afterEach(() => { cleanup(); saveArmConfig.mockClear(); });

describe('SchemaConfigForm', () => {
  it('renders a control per editable field, seeded from config', async () => {
    renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
    expect((screen.getByRole('combobox', { name: /provider/i }) as HTMLSelectElement).value).toBe('tmdb');
    expect(screen.getByLabelText(/tmdb key/i)).toBeInTheDocument();
  });

  it('saves only changed fields, omitting an untouched <hidden> secret', async () => {
    renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
    await fireEvent.change(screen.getByRole('combobox', { name: /provider/i }), { target: { value: 'omdb' } });
    await fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => expect(saveArmConfig).toHaveBeenCalled());
    const payload = saveArmConfig.mock.calls[0][0];
    expect(payload.metadata_provider).toBe('omdb');
    expect('tmdb_api_key' in payload).toBe(false);
  });

  it('includes a secret in the payload when the user types a new value', async () => {
    renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
    await fireEvent.input(screen.getByLabelText(/tmdb key/i), { target: { value: 'new-key' } });
    await fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => expect(saveArmConfig).toHaveBeenCalled());
    expect(saveArmConfig.mock.calls[0][0].tmdb_api_key).toBe('new-key');
  });
});
