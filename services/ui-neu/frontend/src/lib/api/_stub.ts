// Uniform stub for api functions whose v3 backend is MISSING. The calling
// screen is feature-flagged OFF (see $lib/features), so this never fires at
// runtime — it exists so the module type-checks and fails loudly if a hidden
// screen is ever reached. grep `notAvailable(` to find all MISSING calls.
export function notAvailable(feature: string): never {
	throw new Error(`${feature} is not yet available in v3`);
}
