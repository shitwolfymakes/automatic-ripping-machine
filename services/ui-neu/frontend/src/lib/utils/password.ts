// The rules a new password must meet before ARM will change it.

/** The fewest characters a new password may have. */
export const PASSWORD_MIN_LENGTH = 8;

/**
 * The first rule a new password breaks, or null when it meets all three:
 * it differs from the current password, it has at least PASSWORD_MIN_LENGTH
 * characters, and it matches its confirmation. They are checked in that order.
 */
export function passwordProblem(current: string, next: string, confirm: string): string | null {
	if (next === current) return 'New password must differ from the current password';
	if (next.length < PASSWORD_MIN_LENGTH) return `New password must be at least ${PASSWORD_MIN_LENGTH} characters`;
	if (next !== confirm) return 'Passwords do not match';
	return null;
}
