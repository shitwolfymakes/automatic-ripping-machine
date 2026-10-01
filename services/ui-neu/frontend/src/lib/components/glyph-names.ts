export type GlyphName =
	| 'check'
	| 'check-circle'
	| 'x'
	| 'x-circle'
	| 'warning'
	| 'clock'
	| 'chevron-up'
	| 'chevron-down'
	| 'chevron-right'
	| 'arrow-left'
	| 'arrow-right'
	| 'info'
	| 'question-circle'
	| 'shield-check'
	| 'refresh'
	| 'gear'
	| 'folder'
	| 'disc-3'
	| 'copy'
	| 'key'
	| 'eye'
	| 'eye-off'
	| 'lock'
	| 'hard-drive'
	| 'cpu'
	| 'bell'
	| 'loader'
	| 'external-link'
	| 'minus-circle'
	| 'download';

export const GLYPH_PATHS: Record<GlyphName, string> = {
	check: 'M5 13l4 4L19 7',
	'check-circle': 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
	x: 'M6 18L18 6M6 6l12 12',
	'x-circle': 'M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z',
	warning:
		'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z',
	clock: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
	'chevron-up': 'M5 15l7-7 7 7',
	'chevron-down': 'M19 9l-7 7-7-7',
	'chevron-right': 'M9 5l7 7-7 7',
	'arrow-left': 'M10 19l-7-7m0 0l7-7m-7 7h18',
	'arrow-right': 'M14 5l7 7m0 0l-7 7m7-7H3',
	info: 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
	// A "?" mark in a circle (distinct from `info`'s "i"): the original SVG in
	// SchemaConfigForm's Check API Key "unknown" status used this exact path
	// (a fill-rule icon in the source, redrawn here as Glyph's stroke style
	// to fit the shared 24x24 viewBox all other glyphs use).
	'question-circle':
		'M12 21a9 9 0 100-18 9 9 0 000 18zm-1-14a1 1 0 112 0 1 1 0 01-2 0zm0 3a1 1 0 011-1h0a1 1 0 011 1v4a1 1 0 11-2 0v-4z',
	// The udev/drive diagnostics disclosure button's shield-check icon
	// (Settings > Drives).
	'shield-check':
		'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z',
	// The diagnostics "Run Check" button's refresh/circular-arrows icon.
	refresh:
		'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15',
	// DriveCard's rip-speed badge and Drive settings gear icon (same path
	// both places in the original markup).
	gear: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065zM15 12a3 3 0 11-6 0 3 3 0 016 0z',
	// "Rip from ISO" picker: folder rows in the library browser (Task 7,
	// 2026-09-30-iso-source-rip).
	folder: 'M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z',
	// "Rip from ISO" picker + ISO source chip: the disc-3 lucide glyph,
	// flattened to one path in Glyph's stroke style.
	'disc-3': 'M12 21a9 9 0 100-18 9 9 0 000 18zm0-7a2 2 0 100-4 2 2 0 000 4zM6 12a6 6 0 016-6m6 6a6 6 0 01-6 6',
	// First-run setup walkthrough + shared Settings parts (setup spec 2026-10-01).
	copy: 'M8 10a2 2 0 012-2h10a2 2 0 012 2v10a2 2 0 01-2 2H10a2 2 0 01-2-2V10zM4 16a2 2 0 01-2-2V4a2 2 0 012-2h10a2 2 0 012 2',
	key: 'M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z',
	eye: 'M15 12a3 3 0 11-6 0 3 3 0 016 0zM2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z',
	'eye-off':
		'M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21',
	lock: 'M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z',
	'hard-drive':
		'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01',
	cpu: 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z',
	bell: 'M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9',
	// A 3/4 arc; pair with `.spin` for an in-progress indicator.
	loader: 'M21 12a9 9 0 11-6.219-8.56',
	'external-link': 'M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14',
	'minus-circle': 'M15 12H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z',
	download: 'M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4'
};
