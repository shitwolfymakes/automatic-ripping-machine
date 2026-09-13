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
	| 'info';

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
	info: 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z'
};
