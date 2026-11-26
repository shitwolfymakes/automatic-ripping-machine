// HandBrake's PictureRotate value is "angle=N:hflip=0|1".

export type RotateAngle = 0 | 90 | 180 | 270;
export interface Rotate {
	angle: RotateAngle;
	hflip: boolean;
}

export const ROTATE_ANGLES: readonly RotateAngle[] = [0, 90, 180, 270];

// Malformed or missing parts read as angle 0 and no flip.
export function parseRotate(s: string): Rotate {
	const angle = Number(/(?:^|:)angle=(\d+)(?::|$)/.exec(s)?.[1]);
	const hflip = /(?:^|:)hflip=1(?::|$)/.test(s);
	return { angle: ROTATE_ANGLES.find((a) => a === angle) ?? 0, hflip };
}

export function formatRotate(v: Rotate): string {
	return `angle=${v.angle}:hflip=${v.hflip ? 1 : 0}`;
}
