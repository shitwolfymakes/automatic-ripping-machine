import type { GlyphName } from '$lib/ui/glyph-names';
import type { SetupStep, SetupStepState, SetupView } from '$lib/types/api.gen';

// The walkthrough's nine steps, in order (setup spec 2026-10-01 §5).
export interface StepMeta {
	id: SetupStep;
	/** Stepper label. */
	label: string;
	/** Page heading. */
	title: string;
	intro: string;
	optional: boolean;
	/** 'continue': saved on Continue. 'live': the step's controls save as they change. */
	saveHint: 'continue' | 'live';
	/** Skip for now is drawn as a plain button rather than a link. */
	skipEmphasis?: boolean;
}

export const STEPS: StepMeta[] = [
	{
		id: 'account',
		label: 'Secure your account',
		title: 'Secure your account',
		intro: 'Set a new admin password. Everything else in ARM stays locked until you do.',
		optional: false,
		saveHint: 'continue'
	},
	{
		id: 'system',
		label: 'System check',
		title: 'System check',
		intro:
			'ARM checked the folders and services it was installed with. These come from .env and docker-compose, so any fix happens on the server, not here.',
		optional: false,
		saveHint: 'continue'
	},
	{
		id: 'drives',
		label: 'Drives',
		title: 'Drives',
		intro:
			'Enroll the drives you want to rip with. Each enrolled drive gets its own ripper, which takes a few seconds to start.',
		optional: false,
		saveHint: 'live'
	},
	{
		id: 'makemkv',
		label: 'MakeMKV',
		title: 'MakeMKV',
		intro: 'MakeMKV reads and decrypts DVDs and Blu-rays. It needs a key to run.',
		optional: false,
		saveHint: 'continue'
	},
	{
		id: 'metadata',
		label: 'Identification',
		title: 'Identification',
		intro:
			'ARM looks up what is on each disc so your files get the right names. The disc databases, TVmaze and MusicBrainz need no key; TMDb, OMDb and TVDB do.',
		optional: true,
		saveHint: 'continue'
	},
	{
		id: 'discs',
		label: 'Disc handling',
		title: 'How ARM handles discs',
		intro: 'Choose what happens when you insert a disc.',
		optional: false,
		saveHint: 'continue'
	},
	{
		id: 'transcoding',
		label: 'Transcoding',
		title: 'Transcoding',
		intro: 'Encoding turns large rips into smaller files your media server can stream.',
		optional: true,
		saveHint: 'continue'
	},
	{
		id: 'notifications',
		label: 'Notifications',
		title: 'Notifications',
		intro: 'Get told when a rip finishes, needs you, or fails.',
		optional: true,
		saveHint: 'continue',
		skipEmphasis: true
	},
	{
		id: 'finish',
		label: 'Finish',
		title: "You're ready to rip",
		intro: 'Here is what you set up. Anything skipped stays on your dashboard checklist.',
		optional: false,
		saveHint: 'continue'
	}
];

export function stepMeta(id: string): StepMeta | undefined {
	return STEPS.find((s) => s.id === id);
}

export function stepIndex(id: string): number {
	return STEPS.findIndex((s) => s.id === id);
}

export function nextStep(id: SetupStep): SetupStep | null {
	const i = stepIndex(id);
	return i >= 0 && i < STEPS.length - 1 ? STEPS[i + 1].id : null;
}

export function prevStep(id: SetupStep): SetupStep | null {
	const i = stepIndex(id);
	return i > 0 ? STEPS[i - 1].id : null;
}

export type StepUiState = 'not-started' | 'current' | 'done' | 'skipped' | 'attention';

/**
 * A step's recorded state, or null when it has none; a state the UI does not
 * know counts as none.
 */
export function progressState(id: string, progress: SetupView['progress']): SetupStepState | null {
	const state = progress[id]?.state;
	return state === 'done' || state === 'skipped' || state === 'attention' ? state : null;
}

/** A step's state as the summary shows it: recorded, or 'pending'. */
export type SummaryState = SetupStepState | 'pending';

/** The chip a step state is drawn with. */
export interface StateBadge {
	text: string;
	glyph: GlyphName;
	cls: string;
}

/** The chip text, glyph and class for each step state. */
export const STATE_BADGE: Record<SummaryState, StateBadge> = {
	done: { text: 'Done', glyph: 'check', cls: 'chip-success' },
	skipped: { text: 'Skipped', glyph: 'minus-circle', cls: '' },
	attention: { text: 'Needs attention', glyph: 'warning', cls: 'chip-warning' },
	pending: { text: 'Not done', glyph: 'clock', cls: '' }
};

/** The steps summarised after setup: every step but Finish, in order. */
export const REVIEWABLE_STEPS: StepMeta[] = STEPS.filter((s) => s.id !== 'finish');

/** A step setup left open, with its state. */
export interface OpenStep {
	step: StepMeta;
	state: 'skipped' | 'attention';
}

/**
 * The reviewable steps setup left skipped or needing attention, in order;
 * none while progress is undefined (the setup view has not loaded).
 */
export function openSteps(progress: SetupView['progress'] | undefined): OpenStep[] {
	if (!progress) return [];
	const open: OpenStep[] = [];
	for (const step of REVIEWABLE_STEPS) {
		const state = progressState(step.id, progress);
		if (state === 'skipped' || state === 'attention') open.push({ step, state });
	}
	return open;
}

export function uiState(id: SetupStep, current: SetupStep, progress: SetupView['progress']): StepUiState {
	if (id === current) return 'current';
	return progressState(id, progress) ?? 'not-started';
}

export const STATE_WORD: Record<StepUiState, string> = {
	'not-started': 'Not started',
	current: 'Current',
	done: 'Done',
	skipped: 'Skipped',
	attention: 'Needs attention'
};

/** What a step's commit() resolves to: the state to record, 'skip', or false to stay put. */
export type StepCommitResult = 'done' | 'attention' | 'skip' | false;

/** The contract every steps/*Step.svelte implements (bind:this). */
export interface SetupStepComponent {
	commit(): Promise<StepCommitResult>;
}
