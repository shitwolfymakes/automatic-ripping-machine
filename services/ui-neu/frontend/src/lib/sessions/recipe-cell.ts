// One cell of the rip > transcode > output strip.
export interface RecipeCell {
	label: string;
	value?: string | null;
	sub?: string | null;
	mono?: boolean;
	empty?: string;
}
