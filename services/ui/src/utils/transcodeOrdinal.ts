import type { TranscodeTaskView } from '../api/types'

export interface TaskOrdinal {
  n: number
  m: number
}

// Position of `taskId` within its session_application's task set, plus the
// total task count for that application. `n` is 1-based. Returns `null` when
// the task isn't present in `allTasks` (e.g. cancelled/dropped between a poll
// and a render). Sort is by `output_path` ascending — deterministic and
// matches the natural `Track 1`/`Track 2`/… ordering encoded by the templates.
export function taskOrdinal(taskId: string, allTasks: TranscodeTaskView[]): TaskOrdinal | null {
  const me = allTasks.find((t) => t.id === taskId)
  if (me === undefined) return null
  const siblings = allTasks
    .filter((t) => t.session_application_id === me.session_application_id)
    .slice()
    .sort(_compareTasks)
  const idx = siblings.findIndex((t) => t.id === taskId)
  if (idx < 0) return null
  return { n: idx + 1, m: siblings.length }
}

function _compareTasks(a: TranscodeTaskView, b: TranscodeTaskView): number {
  const ap = a.output_path ?? ''
  const bp = b.output_path ?? ''
  if (ap !== bp) return ap < bp ? -1 : 1
  // Tiebreaker keeps siblings stable when paths happen to match
  // (shouldn't with `{track}` in the template, but be safe).
  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0
}
