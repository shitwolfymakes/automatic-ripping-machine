import { writable } from 'svelte/store';

/** Set to true to open the "Rip from ISO" / "Rip from folder" picker on the dashboard. */
export const showIsoPicker = writable(false);

/** Which source the picker offers: an .iso file, or a disc folder (BDMV / VIDEO_TS). */
export const isoPickerMode = writable<'iso' | 'folder'>('iso');
