import type { JobStatus } from '../api/types'

const TERMINAL_JOB_STATUSES: ReadonlySet<JobStatus> = new Set<JobStatus>([
  'ripped',
  'ripped_partial',
  'failed',
  'abandoned',
])

export function isTerminalJobStatus(status: JobStatus): boolean {
  return TERMINAL_JOB_STATUSES.has(status)
}
