import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import SchemaConfigForm from '../SchemaConfigForm.svelte';
import type { SettingsGroup, KeyCheckResponse } from '$lib/types/api.gen';

const saveArmConfig = vi.fn((_config: Record<string, unknown>) => Promise.resolve({ success: true }));
const checkApiKey = vi.fn(
  (_name: string, _value?: string): Promise<KeyCheckResponse> =>
    Promise.resolve({ name: 'tmdb', status: 'ok', detail: null, checked_at: null })
);
vi.mock('$lib/api/settings', () => ({
  saveArmConfig: (config: Record<string, unknown>) => saveArmConfig(config),
  checkApiKey: (name: string, value?: string) => checkApiKey(name, value),
}));

const GROUP: SettingsGroup = {
  name: 'Metadata',
  fields: [
    { key: 'metadata_provider', group: 'Metadata', tier: 'operator', label: 'Provider', help: '', type: 'enum', editable: true, enum_values: ['tmdb', 'omdb'] },
    { key: 'tmdb_api_key', group: 'Metadata', tier: 'secret', label: 'TMDb key', help: '', type: 'string', editable: true, enum_values: null },
    { key: 'makemkv_key', group: 'Metadata', tier: 'secret', label: 'MakeMKV key', help: '', type: 'string', editable: true, enum_values: null },
  ],
};
const CONFIG = { metadata_provider: 'tmdb', tmdb_api_key: '<hidden>', makemkv_key: '<hidden>' };

afterEach(() => { cleanup(); saveArmConfig.mockClear(); checkApiKey.mockClear(); });

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

describe('SchemaConfigForm key-check button', () => {
  function tmdbCheckButton() {
    // testid div -> .flex-1 wrapper -> the "flex items-end gap-2" row that
    // also holds the Check button as a sibling.
    return screen
      .getByTestId('setting-tmdb_api_key')
      .parentElement!.parentElement!.querySelector('button')!;
  }

  it('calls checkApiKey with the unsaved value when the user typed a new key', async () => {
    renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
    await fireEvent.input(screen.getByLabelText(/tmdb key/i), { target: { value: 'unsaved-key' } });
    await fireEvent.click(tmdbCheckButton());
    await waitFor(() => expect(checkApiKey).toHaveBeenCalledWith('tmdb', 'unsaved-key'));
  });

  it('calls checkApiKey with no value for an untouched <hidden> secret', async () => {
    renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
    await fireEvent.click(tmdbCheckButton());
    await waitFor(() => expect(checkApiKey).toHaveBeenCalledWith('tmdb', undefined));
  });

  it('shows "Checking..." disabled while the probe runs, then renders the ok result', async () => {
    let resolve!: (v: KeyCheckResponse) => void;
    checkApiKey.mockImplementation(
      (name: string) =>
        new Promise<KeyCheckResponse>((r) => {
          // makemkv's onMount auto-run resolves immediately so it doesn't
          // block the test; only the tmdb click's promise stays pending.
          if (name === 'makemkv') r({ name, status: 'unknown', detail: 'not checked yet', checked_at: null });
          else resolve = r;
        })
    );
    renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
    await fireEvent.click(tmdbCheckButton());
    expect(screen.getByRole('button', { name: /checking/i })).toBeDisabled();
    resolve({ name: 'tmdb', status: 'ok', detail: null, checked_at: '2026-09-05T00:00:00Z' });
    await waitFor(() => expect(screen.getByTestId('key-check-tmdb_api_key')).toHaveTextContent(/valid/i));
  });

  it('renders the invalid result with its detail', async () => {
    checkApiKey.mockImplementation((name: string) =>
      Promise.resolve(
        name === 'tmdb'
          ? { name, status: 'invalid', detail: 'TMDb rejected the key', checked_at: null }
          : { name, status: 'unknown', detail: 'not checked yet', checked_at: null }
      )
    );
    renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
    await fireEvent.click(tmdbCheckButton());
    await waitFor(() =>
      expect(screen.getByTestId('key-check-tmdb_api_key')).toHaveTextContent('TMDb rejected the key')
    );
  });

  it('renders the missing result', async () => {
    checkApiKey.mockImplementation((name: string) =>
      Promise.resolve(
        name === 'tmdb'
          ? { name, status: 'missing', detail: 'no key set', checked_at: null }
          : { name, status: 'unknown', detail: 'not checked yet', checked_at: null }
      )
    );
    renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
    await fireEvent.click(tmdbCheckButton());
    await waitFor(() => expect(screen.getByTestId('key-check-tmdb_api_key')).toHaveTextContent(/no key set/i));
  });

  it('renders the unknown result with its detail', async () => {
    checkApiKey.mockImplementation((name: string) =>
      Promise.resolve(
        name === 'tmdb'
          ? { name, status: 'unknown', detail: 'save the key; the ripper verifies it before the next rip', checked_at: null }
          : { name, status: 'unknown', detail: 'not checked yet', checked_at: null }
      )
    );
    renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
    await fireEvent.click(tmdbCheckButton());
    await waitFor(() =>
      expect(screen.getByTestId('key-check-tmdb_api_key')).toHaveTextContent(
        'save the key; the ripper verifies it before the next rip'
      )
    );
  });

  it('renders the error result with its detail', async () => {
    checkApiKey.mockImplementation((name: string) =>
      Promise.resolve(
        name === 'tmdb'
          ? { name, status: 'error', detail: 'transport error: boom', checked_at: null }
          : { name, status: 'unknown', detail: 'not checked yet', checked_at: null }
      )
    );
    renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
    await fireEvent.click(tmdbCheckButton());
    await waitFor(() => expect(screen.getByTestId('key-check-tmdb_api_key')).toHaveTextContent('transport error: boom'));
  });

  it('shows the checked-at time on an ok result', async () => {
    checkApiKey.mockImplementation((name: string) =>
      Promise.resolve(
        name === 'tmdb'
          ? { name, status: 'ok', detail: null, checked_at: '2026-09-05T00:00:00Z' }
          : { name, status: 'unknown', detail: 'not checked yet', checked_at: null }
      )
    );
    renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
    await fireEvent.click(tmdbCheckButton());
    await waitFor(() => expect(screen.getByTestId('key-check-tmdb_api_key')).toHaveTextContent(/checked/i));
  });

  it('auto-runs the makemkv check on mount', async () => {
    checkApiKey.mockImplementation((name: string) =>
      Promise.resolve(
        name === 'makemkv'
          ? { name: 'makemkv', status: 'ok', detail: null, checked_at: '2026-09-05T00:00:00Z' }
          : { name, status: 'ok', detail: null, checked_at: null }
      )
    );
    renderComponent(SchemaConfigForm, { props: { group: GROUP, config: CONFIG } });
    await waitFor(() => expect(checkApiKey).toHaveBeenCalledWith('makemkv', undefined));
    await waitFor(() => expect(screen.getByTestId('key-check-makemkv_key')).toHaveTextContent(/valid/i));
    expect(screen.getAllByRole('button', { name: /check api key/i }).length).toBeGreaterThan(0);
  });
});
