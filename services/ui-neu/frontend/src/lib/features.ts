// Whole-screen feature flags. Screens whose v3 backend is entirely MISSING are
// disabled here so the app boots and hides them; they flip to true when their
// backlog tier lands a v3 backend. (Per the verified BFF->v3 route inventory.)
export const features = {
	dashboard: true,
	notifications: true,
	logs: true,
	settings: true,
	transcoder: true, // additionally gated at runtime by transcoderEnabled
	files: false, // file-browser API MISSING in v3
	setup: false // setup-status/complete API MISSING in v3
} as const;

const ROUTE_FLAGS: Record<string, keyof typeof features> = {
	'/': 'dashboard',
	'/notifications': 'notifications',
	'/logs': 'logs',
	'/settings': 'settings',
	'/transcoder': 'transcoder',
	'/files': 'files',
	'/setup': 'setup'
};

// Map a route path to its flag; unknown routes default to enabled.
export function isScreenEnabled(path: string): boolean {
	const key = ROUTE_FLAGS[path];
	return key === undefined ? true : features[key];
}
