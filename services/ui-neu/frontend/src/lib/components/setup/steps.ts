import type { SetupStep, SetupView } from '$lib/types/api.gen';

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
		label: 'Find titles',
		title: 'Find titles',
		intro: 'ARM looks up what is on each disc so your files get the right names.',
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
		saveHint: 'continue'
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

export function uiState(id: SetupStep, current: SetupStep, progress: SetupView['progress']): StepUiState {
	if (id === current) return 'current';
	const p = progress[id]?.state;
	return p === 'done' ? 'done' : p === 'skipped' ? 'skipped' : p === 'attention' ? 'attention' : 'not-started';
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
