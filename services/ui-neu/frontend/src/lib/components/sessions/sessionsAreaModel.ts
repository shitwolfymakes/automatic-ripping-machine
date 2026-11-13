import type { SidebarMode } from '$lib/handbrake/sidebarModel';
import type { RipPresetView, SessionView, TranscodePresetView } from '$lib/types/api.gen';
import { isPassthroughSession, presetToolMap, PASSTHROUGH_TOOL } from '$lib/utils/sessions';

export type View = 'sessions' | 'rip' | 'transcode' | 'routing';

export type ViewCounts = Partial<Record<View, number>>;

export interface ViewTab {
	key: View;
	label: string;
	count: number | undefined;
}

const TABS: ReadonlyArray<{ key: View; label: string }> = [
	{ key: 'sessions', label: 'Sessions' },
	{ key: 'rip', label: 'Rip presets' },
	{ key: 'transcode', label: 'Transcode presets' },
	{ key: 'routing', label: 'Routing' }
];

// Which editors are open: the session builder, and the rip and transcode
// preset sidebars. Editors can stack (a preset sidebar opens over the builder).
export interface EditorState {
	builderOpen: boolean;
	sessionId: string | null;
	ripPresetId: string | null;
	transcodePresetId: string | null;
}

export function viewTabs(counts: ViewCounts): ViewTab[] {
	return TABS.map((tab) => ({ ...tab, count: counts[tab.key] }));
}

// The session whose builder is open, highlighted in its table.
export function activeSessionKey(editor: EditorState): string | null {
	return editor.builderOpen ? editor.sessionId : null;
}

// The preset whose editor is open, highlighted in its table.
export function activePresetKey(editor: EditorState): string | null {
	return editor.transcodePresetId ?? editor.ripPresetId;
}

// A preset sidebar opened from the builder sits above it.
export function isSidebarStacked(editor: EditorState): boolean {
	return editor.builderOpen;
}

// A failed delete keeps its editor open; a deleted item has nothing left to edit.
export function shouldCloseBuilderAfterDelete(deletedId: string, deleted: boolean, editor: EditorState): boolean {
	return deleted && deletedId === activeSessionKey(editor);
}

export function shouldClosePresetEditorsAfterDelete(deletedId: string, deleted: boolean, editor: EditorState): boolean {
	return deleted && deletedId === activePresetKey(editor);
}

export function transcodeSidebarMode(preset: TranscodePresetView): SidebarMode {
	return preset.is_builtin ? 'view' : 'edit';
}

export function isRipSidebarReadOnly(preset: RipPresetView | null): boolean {
	return preset?.is_builtin ?? false;
}

// Only a newly created preset is pre-selected in the builder, not an edited one.
export function isCreatingRipPreset(sidebar: { preset: RipPresetView | null } | null): boolean {
	return sidebar?.preset === null;
}

export function isCreatingTranscodePreset(sidebar: { mode: SidebarMode } | null): boolean {
	return sidebar?.mode === 'new';
}

export function deleteSessionMessage(target: { name: string } | null): string {
	return target ? `Delete the session "${target.name}"? This cannot be undone.` : '';
}

export function deletePresetMessage(target: { name: string } | null): string {
	return target ? `Delete the preset "${target.name}"? This cannot be undone.` : '';
}

// A ripper-only deployment (not transcode-capable) can never run encode work,
// so it shows only passthrough sessions and presets.
export function passthroughSessions<S extends SessionView>(
	sessions: S[],
	transcodePresets: TranscodePresetView[]
): S[] {
	const tools = presetToolMap(transcodePresets);
	return sessions.filter((s) => isPassthroughSession(s, tools));
}

export function passthroughTranscodePresets(presets: TranscodePresetView[]): TranscodePresetView[] {
	return presets.filter((p) => p.tool === PASSTHROUGH_TOOL);
}
