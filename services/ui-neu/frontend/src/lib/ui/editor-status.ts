// What a form embedded in an EditorSidebar tells the sidebar's footer: whether
// a save is in flight, and an optional note for the footer's usage line.
export interface EditorStatus {
	submitting: boolean;
	note: string;
}

export const IDLE_STATUS: EditorStatus = { submitting: false, note: '' };
