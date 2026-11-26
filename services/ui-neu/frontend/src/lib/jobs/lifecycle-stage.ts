// The lifecycle stage ids, kept apart from `lifecycle.ts` so `status-groups.ts`
// can name them without importing the module that imports it back.
export type LifecycleStageId = 'waiting' | 'identifying' | 'ripping' | 'transcoding' | 'complete';
