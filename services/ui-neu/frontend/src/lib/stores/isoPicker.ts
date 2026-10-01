import { writable } from 'svelte/store';

/** Set to true to open the "Rip from ISO" picker on the dashboard. */
export const showIsoPicker = writable(false);
