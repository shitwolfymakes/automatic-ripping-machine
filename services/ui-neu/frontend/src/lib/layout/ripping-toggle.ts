/**
 * The header toggle's label. Paused with Review first on holds new discs for
 * review (they park instead of being refused); paused without it refuses them.
 */
export function rippingToggleLabel(rippingEnabled: boolean, holdForReview: boolean): string {
	if (rippingEnabled) return 'Auto-Start';
	return holdForReview ? 'Hold for Review' : 'Paused';
}
