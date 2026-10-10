<script lang="ts">
    import { onDestroy, onMount } from 'svelte';
    import type { Scheme, Preset, Overrides, PresetEditorState } from '$lib/types/presets';
    import { listHandbrakePresets } from '$lib/api/transcoder';
    interface Props {
        scope: 'global' | 'job';
        initialState: PresetEditorState;
        scheme: Scheme | null;
        presets: Preset[];
        offline: boolean;
        saving: boolean;
        onSave: (state: PresetEditorState) => Promise<void>;
        onSaveAsNew?: (state: { name: string; parent_slug: string; overrides: Overrides }) => Promise<void>;
        onRetry?: () => void;
    }

    let { scope, initialState, scheme, presets, offline, saving, onSave, onSaveAsNew, onRetry }: Props = $props();

    const initialSlug = initialState.preset_slug;
    let selectedSlug = $state<string>(initialSlug);
    let overrides = $state<Overrides>({
        shared: structuredClone(initialState.overrides?.shared ?? {}),
        tiers: structuredClone(initialState.overrides?.tiers ?? {})
    });

    // Once presets are loaded, default to the first built-in if no slug was preselected
    $effect(() => {
        if (selectedSlug === '' && presets.length > 0) {
            const firstBuiltin = presets.find(p => p.builtin && !p.unavailable);
            if (firstBuiltin) selectedSlug = firstBuiltin.slug;
        }
    });

    const dirtyCount = $derived(
        Object.keys(overrides.shared).length +
        Object.values(overrides.tiers).reduce((n, t) => n + Object.keys(t).length, 0)
    );
    const dirty = $derived(dirtyCount > 0);
    const selectedPreset = $derived(presets.find(p => p.slug === selectedSlug));
    const isUnavailable = $derived(selectedPreset?.unavailable === true);
    const canSave = $derived(!saving && !isUnavailable && (dirty || selectedSlug !== initialSlug));

    const builtinCount = $derived(presets.filter(p => p.builtin && !p.unavailable).length);
    const customCount = $derived(presets.filter(p => !p.builtin && !p.unavailable).length);

    function setShared(key: string, value: unknown) {
        if (value === '' || value === null || value === undefined) {
            delete overrides.shared[key];
        } else {
            overrides.shared[key] = value;
        }
        overrides = { ...overrides };
    }

    function setTier(tier: string, key: string, value: unknown) {
        if (!overrides.tiers[tier]) overrides.tiers[tier] = {};
        if (value === '' || value === null || value === undefined) {
            delete overrides.tiers[tier][key];
            if (Object.keys(overrides.tiers[tier]).length === 0) delete overrides.tiers[tier];
        } else {
            overrides.tiers[tier][key] = value;
        }
        overrides = { ...overrides };
    }

    function effectiveShared(key: string): unknown {
        if (key in overrides.shared) return overrides.shared[key];
        return selectedPreset?.shared?.[key] ?? '';
    }

    function effectiveTier(tier: string, key: string): unknown {
        if (overrides.tiers[tier]?.[key] !== undefined) return overrides.tiers[tier][key];
        const tierVal = selectedPreset?.tiers?.[tier]?.[key];
        if (tierVal !== undefined) return tierVal;
        return selectedPreset?.shared?.[key] ?? '';
    }

    function isSharedDirty(key: string): boolean {
        return key in overrides.shared;
    }

    function isTierDirty(tier: string, key: string): boolean {
        return overrides.tiers[tier]?.[key] !== undefined;
    }

    const TIER_LABELS: Record<string, string> = { dvd: 'DVD', bluray: 'Blu-ray', uhd: 'UHD' };
    const TIER_HINTS: Record<string, string> = { dvd: '< 720p', bluray: '720p-1080p', uhd: '> 1080p' };

    let saveAsModalOpen = $state(false);
    let newPresetName = $state('');
    let saveAsNewError = $state<string>('');

    let undoToast = $state<{ message: string; previous: { slug: string; overrides: Overrides } } | null>(null);
    let undoTimer: ReturnType<typeof setTimeout> | null = null;
    onDestroy(() => { if (undoTimer) clearTimeout(undoTimer); });

    // HandBrake preset picker. The transcoder enumerates its built-in
    // preset list via /api/v1/handbrake-presets; the BFF passes through.
    // When the list is empty (transcoder offline, older version, parser
    // failure) we fall back to free-text entry so the field is never
    // un-editable.
    let handbrakePresetGroups = $state<Record<string, string[]>>({});
    const handbrakeKnown = $derived(
        new Set(Object.values(handbrakePresetGroups).flat())
    );
    const handbrakeAvailable = $derived(handbrakeKnown.size > 0);
    onMount(async () => {
        // listHandbrakePresets is MISSING in v3 (no handbrake-presets endpoint)
        // and rejects via the notAvailable stub. The empty fallback is the agreed
        // sentinel — the field drops to free-text entry, never un-editable.
        try {
            handbrakePresetGroups = await listHandbrakePresets();
        } catch {
            handbrakePresetGroups = {};
        }
    });

    function handleDropdownChange(newSlug: string) {
        const wasDirty = dirty;
        const previousSlug = selectedSlug;
        const previousName = selectedPreset?.name ?? previousSlug;
        const previousOverrides: Overrides = JSON.parse(JSON.stringify(overrides));
        selectedSlug = newSlug;
        overrides = { shared: {}, tiers: {} };
        if (wasDirty) {
            const totalCleared = Object.keys(previousOverrides.shared).length +
                Object.values(previousOverrides.tiers).reduce((n, t) => n + Object.keys(t).length, 0);
            undoToast = {
                message: `Cleared ${totalCleared} ${totalCleared === 1 ? 'change' : 'changes'} from ${previousName}`,
                previous: { slug: previousSlug, overrides: previousOverrides }
            };
            if (undoTimer) clearTimeout(undoTimer);
            undoTimer = setTimeout(() => { undoToast = null; }, 5000);
        }
    }

    function handleUndo() {
        if (!undoToast) return;
        selectedSlug = undoToast.previous.slug;
        overrides = undoToast.previous.overrides;
        undoToast = null;
        if (undoTimer) { clearTimeout(undoTimer); undoTimer = null; }
    }

    function handleSave() {
        if (!canSave) return;
        onSave({ preset_slug: selectedSlug, overrides: $state.snapshot(overrides) as Overrides });
    }

    function handleRevert() {
        overrides = { shared: {}, tiers: {} };
        selectedSlug = initialSlug;
    }

    async function handleSaveAsConfirm() {
        if (!onSaveAsNew || !newPresetName.trim()) return;
        saveAsNewError = '';
        try {
            await onSaveAsNew({
                name: newPresetName.trim(),
                parent_slug: selectedSlug,
                overrides: $state.snapshot(overrides) as Overrides,
            });
            saveAsModalOpen = false;
            newPresetName = '';
        } catch (e: unknown) {
            saveAsNewError = e instanceof Error ? e.message : 'Save failed';
        }
    }

    function disabledSaveReason(): string {
        if (saving) return 'Saving...';
        if (isUnavailable) return 'Selected preset is not available in the active scheme';
        if (!dirty && selectedSlug === initialSlug) return 'No changes to save';
        return '';
    }

    function slugify(name: string): string {
        return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'custom';
    }
</script>

{#if offline || !scheme}
    <div class="alert alert-warning preset-editor-offline">
        <p class="alert-title">Transcoder service unavailable</p>
        <p class="alert-body">Cannot load preset options. Check that arm-transcoder is running.</p>
        {#if onRetry}
            <button onclick={onRetry} class="btn btn-warning btn-sm preset-editor-retry-btn">
                Retry
            </button>
        {/if}
    </div>
{:else}
    <div class="stack">
        {#if isUnavailable}
            <div class="alert alert-warning">
                This preset was built for scheme <strong>{selectedPreset?.scheme}</strong> but the active scheme is <strong>{scheme.slug}</strong>. Pick a compatible preset to save changes.
            </div>
        {/if}
        <div class="preset-editor-scheme-row">
            <div>
                <p class="eyebrow">Active scheme</p>
                <p class="preset-editor-scheme-name">{scheme.name}</p>
            </div>
            <p class="preset-editor-scheme-count">{builtinCount} built-in | {customCount} custom</p>
        </div>
        <label class="field">
            <span class="field-label">Preset</span>
            <select
                id="preset-select"
                value={selectedSlug}
                onchange={(e) => handleDropdownChange((e.target as HTMLSelectElement).value)}
                disabled={saving}
            >
                <optgroup label="Built-in">
                    {#each presets.filter(p => p.builtin && !p.unavailable) as p (p.slug)}
                        <option value={p.slug}>{p.name}</option>
                    {/each}
                </optgroup>
                {#if presets.some(p => !p.builtin && !p.unavailable)}
                    <optgroup label="Custom">
                        {#each presets.filter(p => !p.builtin && !p.unavailable) as p (p.slug)}
                            <option value={p.slug}>{p.name}</option>
                        {/each}
                    </optgroup>
                {/if}
                {#if presets.some(p => p.unavailable)}
                    <optgroup label="Unavailable (other scheme)">
                        {#each presets.filter(p => p.unavailable) as p (p.slug)}
                            <option value={p.slug} disabled title={p.reason}>{p.name} ({p.scheme})</option>
                        {/each}
                    </optgroup>
                {/if}
            </select>
            {#if selectedPreset?.description}
                <span class="field-help">{selectedPreset.description}</span>
            {/if}
        </label>

        <div>
            <div class="preset-editor-customize-head">
                <h4 class="preset-editor-customize-title">Customize</h4>
                {#if dirty}
                    <span class="badge preset-editor-dirty-count">
                        {dirtyCount} {dirtyCount === 1 ? 'change' : 'changes'}
                    </span>
                {/if}
            </div>

            <div class="stack stack-sm preset-editor-tiers">
                <div class="panel-section">
                    <p class="eyebrow preset-editor-tier-heading">Shared</p>
                    <div class="grid-2">
                        <label class="field">
                            <span class="field-label preset-editor-sub-label">Audio encoder</span>
                            <div data-dirty={isSharedDirty('audio_encoder')} class="preset-editor-dirty-wrap">
                                <select
                                    value={effectiveShared('audio_encoder')}
                                    onchange={(e) => setShared('audio_encoder', (e.target as HTMLSelectElement).value)}
                                    disabled={saving || isUnavailable}
                                >
                                    {#each scheme.supported_audio_encoders as enc}
                                        <option value={enc}>{enc}</option>
                                    {/each}
                                </select>
                            </div>
                        </label>
                        <label class="field">
                            <span class="field-label preset-editor-sub-label">Subtitle mode</span>
                            <div data-dirty={isSharedDirty('subtitle_mode')} class="preset-editor-dirty-wrap">
                                <select
                                    value={effectiveShared('subtitle_mode')}
                                    onchange={(e) => setShared('subtitle_mode', (e.target as HTMLSelectElement).value)}
                                    disabled={saving || isUnavailable}
                                >
                                    {#each scheme.supported_subtitle_modes as mode}
                                        <option value={mode}>{mode}</option>
                                    {/each}
                                </select>
                            </div>
                        </label>
                    </div>
                </div>

                {#each ['dvd', 'bluray', 'uhd'] as tier}
                    <div class="panel-section">
                        <p class="eyebrow preset-editor-tier-heading">
                            {TIER_LABELS[tier]} <span class="preset-editor-tier-hint">| {TIER_HINTS[tier]}</span>
                        </p>
                        <div class="preset-editor-tier-grid">
                            <label class="field">
                                <span class="field-label preset-editor-sub-label">Encoder</span>
                                <div data-dirty={isTierDirty(tier, 'video_encoder')} class="preset-editor-dirty-wrap">
                                    <select
                                        value={effectiveTier(tier, 'video_encoder')}
                                        onchange={(e) => setTier(tier, 'video_encoder', (e.target as HTMLSelectElement).value)}
                                        disabled={saving || isUnavailable}
                                    >
                                        {#each scheme.supported_encoders as enc}
                                            <option value={enc.slug}>{enc.name}</option>
                                        {/each}
                                    </select>
                                </div>
                            </label>
                            <label class="field">
                                <span class="field-label preset-editor-sub-label">Quality (CRF 0-51)</span>
                                <div data-dirty={isTierDirty(tier, 'video_quality')} class="preset-editor-dirty-wrap">
                                    <input
                                        type="number" min="0" max="51" step="1"
                                        data-testid="tier-{tier}-quality"
                                        value={effectiveTier(tier, 'video_quality')}
                                        oninput={(e) => {
                                            const raw = (e.target as HTMLInputElement).value;
                                            setTier(tier, 'video_quality', raw === '' ? '' : Number(raw));
                                        }}
                                        disabled={saving || isUnavailable}
                                    />
                                </div>
                            </label>
                            <label class="field preset-editor-handbrake-field">
                                <span class="field-label preset-editor-sub-label">HandBrake preset</span>
                                <div data-dirty={isTierDirty(tier, 'handbrake_preset')} class="preset-editor-dirty-wrap">
                                    {#if handbrakeAvailable && handbrakeKnown.has(String(effectiveTier(tier, 'handbrake_preset')))}
                                        <select
                                            value={effectiveTier(tier, 'handbrake_preset')}
                                            onchange={(e) => {
                                                const v = (e.target as HTMLSelectElement).value;
                                                setTier(tier, 'handbrake_preset', v === '__custom__' ? '' : v);
                                            }}
                                            disabled={saving || isUnavailable}
                                        >
                                            {#each Object.entries(handbrakePresetGroups) as [category, names]}
                                                <optgroup label={category}>
                                                    {#each names as name}
                                                        <option value={name}>{name}</option>
                                                    {/each}
                                                </optgroup>
                                            {/each}
                                            <option value="__custom__">Custom...</option>
                                        </select>
                                    {:else}
                                        <input
                                            type="text"
                                            value={effectiveTier(tier, 'handbrake_preset')}
                                            oninput={(e) => setTier(tier, 'handbrake_preset', (e.target as HTMLInputElement).value)}
                                            disabled={saving || isUnavailable}
                                            placeholder={handbrakeAvailable ? 'Custom preset name' : 'HandBrake preset name'}
                                        />
                                    {/if}
                                </div>
                                {#if handbrakeAvailable && handbrakeKnown.has(String(effectiveTier(tier, 'handbrake_preset')))}
                                    <button
                                        type="button"
                                        class="btn btn-link btn-sm"
                                        onclick={() => setTier(tier, 'handbrake_preset', '')}
                                    >Use a custom preset name</button>
                                {/if}
                            </label>
                            {#each Object.entries(scheme.advanced_fields ?? {}) as [key, def]}
                                <label class="field">
                                    <span class="field-label preset-editor-sub-label">{key}</span>
                                    <div data-dirty={isTierDirty(tier, key)} class="preset-editor-dirty-wrap">
                                        {#if def.type === 'enum' && def.values}
                                            <select
                                                value={effectiveTier(tier, key) || def.default || ''}
                                                onchange={(e) => setTier(tier, key, (e.target as HTMLSelectElement).value)}
                                                disabled={saving || isUnavailable}
                                            >
                                                {#each def.values as v}
                                                    <option value={v}>{v}</option>
                                                {/each}
                                            </select>
                                        {:else}
                                            <input
                                                type="text"
                                                value={effectiveTier(tier, key)}
                                                oninput={(e) => setTier(tier, key, (e.target as HTMLInputElement).value)}
                                                disabled={saving || isUnavailable}
                                            />
                                        {/if}
                                    </div>
                                    {#if def.description}
                                        <span class="field-help preset-editor-advanced-desc">{def.description}</span>
                                    {/if}
                                </label>
                            {/each}
                        </div>
                    </div>
                {/each}
            </div>
        </div>

        <div class="preset-editor-save-bar">
            <div class="preset-editor-save-actions">
                <button
                    type="button"
                    onclick={handleSave}
                    disabled={!canSave}
                    title={disabledSaveReason()}
                    class="btn btn-primary"
                >
                    {saving ? 'Saving...' : 'Save changes'}
                </button>
                {#if scope === 'global' && onSaveAsNew}
                    <button
                        type="button"
                        onclick={() => { saveAsModalOpen = true; newPresetName = ''; saveAsNewError = ''; }}
                        disabled={!dirty}
                        class="btn preset-editor-save-as-btn"
                    >
                        Save as new preset
                    </button>
                {/if}
            </div>
            <button
                type="button"
                onclick={handleRevert}
                disabled={!dirty && selectedSlug === initialSlug}
                class="btn btn-link preset-editor-revert-btn"
            >
                Revert
            </button>
        </div>
    </div>

    {#if undoToast}
        <div class="toast preset-editor-undo-toast">
            <span class="toast-body">
                {undoToast.message}
                <button onclick={handleUndo} class="preset-editor-undo-btn">Undo</button>
            </span>
        </div>
    {/if}

    {#if saveAsModalOpen}
        <div class="modal" role="dialog" aria-modal="true" aria-labelledby="save-as-heading">
            <div class="modal-panel preset-editor-save-as-panel">
                <h3 id="save-as-heading" class="modal-title">Save as new preset</h3>
                <p class="modal-body">
                    Saves your current customizations as a new preset based on <strong>{selectedPreset?.name}</strong>.
                </p>
                <label class="field preset-editor-save-as-field">
                    <span class="field-label">Name</span>
                    <input
                        type="text"
                        bind:value={newPresetName}
                        placeholder="e.g. Weekend Rips"
                    />
                    {#if newPresetName.trim()}
                        <span class="field-help">Will be saved as: <code>{slugify(newPresetName)}</code></span>
                    {/if}
                    {#if saveAsNewError}
                        <span class="field-error">{saveAsNewError}</span>
                    {/if}
                </label>
                <div class="modal-actions">
                    <button type="button" onclick={() => { saveAsModalOpen = false; }}
                            class="btn btn-ghost">
                        Cancel
                    </button>
                    <button type="button" onclick={handleSaveAsConfirm}
                            disabled={!newPresetName.trim()}
                            class="btn btn-primary">
                        Create preset
                    </button>
                </div>
            </div>
        </div>
    {/if}
{/if}

<style>
	/* alert's default padding is 0.5rem/0.75rem; the original offline
	   banner was p-4 (1rem all round), a bigger standalone notice than an
	   inline alert strip. */
	.preset-editor-offline { padding: 1rem; }
	/* original Retry: solid amber-600 fill with white text, not btn-warning's
	   outlined look. */
	.preset-editor-retry-btn { margin-top: 0.5rem; border-color: var(--color-warning); background: var(--color-warning); color: var(--color-on-primary); }
	/* darken-on-hover without a literal colour: no --color-warning-hover
	   token exists (unlike --color-primary-hover), and color-mix against a
	   text token would flip direction between light/dark; a brightness
	   filter reproduces the darkened solid fill in both themes. */
	.preset-editor-retry-btn:hover { filter: brightness(0.85); }
	.preset-editor-scheme-row { display: flex; align-items: baseline; justify-content: space-between; border-bottom: 1px solid var(--color-border); padding-bottom: 0.5rem; }
	.preset-editor-scheme-name { font-size: 1rem; font-weight: 600; color: var(--color-text); }
	.preset-editor-scheme-count { font-size: 0.75rem; color: var(--color-text-muted); }
	.preset-editor-customize-head { display: flex; align-items: center; justify-content: space-between; }
	.preset-editor-customize-title { font-size: 0.875rem; font-weight: 600; color: var(--color-text-secondary); }
	/* original dirty-count pill: bg-primary/20 text-primary, a heavier tint
	   than badge's default (primary-tint-2/primary-text). */
	.preset-editor-dirty-count { background: var(--color-primary-tint-3); color: var(--color-primary); }
	.preset-editor-tiers { margin-top: 0.75rem; }
	.preset-editor-tier-heading { margin-bottom: 0.5rem; }
	.preset-editor-tier-hint { color: var(--color-text-faint); }
	/* original: grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 - no 4-column grid
	   helper exists (layout.css only goes to grid-3). */
	.preset-editor-tier-grid { display: grid; grid-template-columns: 1fr; gap: 0.75rem; }
	@media (min-width: 640px) { .preset-editor-tier-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
	@media (min-width: 1024px) { .preset-editor-tier-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
	/* original sub-labels were text-xs (0.75rem), not field-label's own
	   text-sm (0.875rem) - these are secondary labels inside a nested
	   panel-section, a visually smaller role than a top-level field label. */
	.preset-editor-sub-label { font-size: 0.75rem; line-height: 1rem; font-weight: 400; color: var(--color-text-muted); }
	/* the dirty-ring wrapper: rounded-lg ring-2 ring-primary/40 around the
	   control when this field carries an override. */
	.preset-editor-dirty-wrap[data-dirty="true"] { border-radius: var(--radius-lg); box-shadow: 0 0 0 2px color-mix(in srgb, var(--color-primary) 40%, transparent); }
	.preset-editor-handbrake-field { grid-column: span 1; }
	@media (min-width: 1024px) { .preset-editor-handbrake-field { grid-column: span 2; } }
	.preset-editor-advanced-desc { display: block; color: var(--color-text-faint); }
	.preset-editor-save-bar { display: flex; align-items: center; justify-content: space-between; border-top: 1px solid var(--color-border); padding-top: 0.75rem; }
	.preset-editor-save-actions { display: flex; align-items: center; gap: 0.75rem; }
	/* original save button: bg-primary px-4 py-1.5 font-semibold - .btn-primary's
	   default padding (py-0.5rem) is 2px taller per side than this button's
	   original py-1.5 (0.375rem). */
	.preset-editor-save-actions > :first-child { padding-top: 0.375rem; padding-bottom: 0.375rem; font-weight: 600; }
	/* original "Save as new preset": outlined primary-coloured button
	   (border-primary text-primary hover:bg-primary/10), close to bare .btn
	   but with the solid primary border colour and semibold weight instead
	   of .btn's border-strong/font-medium. */
	.preset-editor-save-as-btn { border-color: var(--color-primary); color: var(--color-primary); font-weight: 600; padding-top: 0.5rem; padding-bottom: 0.5rem; }
	.preset-editor-save-as-btn:hover { background: var(--color-primary-tint-2); }
	.preset-editor-revert-btn { color: var(--color-text-muted); }
	.preset-editor-revert-btn:hover { color: var(--color-text-secondary); background: none; text-decoration: none; }
	/* original: fixed bottom-4 left-1/2 -translate-x-1/2, a solid dark bar
	   with always-white text regardless of theme. The strict token set
	   forbids the literal rgb(17 24 39)/white values that were here - the
	   `toast` block's own surface-raised/tone-accent look is used instead,
	   with only the fixed bottom-centre position kept scoped; any visible
	   difference from the original's own always-dark bar is a deviation. */
	.preset-editor-undo-toast { position: fixed; bottom: 1rem; left: 50%; z-index: 40; transform: translateX(-50%); }
	.preset-editor-undo-btn { margin-left: 0.75rem; background: none; border: 0; padding: 0; color: inherit; font: inherit; text-decoration: underline; cursor: pointer; }
	.preset-editor-save-as-panel { padding: 1.25rem; }
	.preset-editor-save-as-field { margin-top: 0.75rem; }
</style>
