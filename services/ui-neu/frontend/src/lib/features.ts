// Whole-screen feature flags. Screens with no v3 backend are
// disabled here so the app boots and hides them; each flips to true once its backend exists.
export const features = {
	dashboard: true,
	notifications: true,
	logs: true, // job-scoped log browser (GET /api/logs/{job_id}); see routes/logs/
	settings: true,
	transcoder: true, // additionally gated at runtime by transcoderEnabled
	files: true,
	// In-screen flags (not in ROUTE_FLAGS): they hide entry points inside a screen.
	maintenance: false // Files orphan folders + transcoder job cleanup: APIs MISSING in v3
} as const;

const ROUTE_FLAGS: Record<string, keyof typeof features> = {
	'/': 'dashboard',
	'/notifications': 'notifications',
	'/logs': 'logs',
	'/settings': 'settings',
	'/transcoder': 'transcoder',
	'/files': 'files'
};

// Map a route path to its flag; unknown routes default to enabled.
export function isScreenEnabled(path: string): boolean {
	const key = ROUTE_FLAGS[path];
	return key === undefined ? true : features[key];
}
