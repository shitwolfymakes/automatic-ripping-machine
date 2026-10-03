import { describe, expect, it } from 'vitest'
import type { DriveView } from '../api/types'
import {
  driveStatusLabel,
  identityLine,
  isRipping,
  partitionDrives,
  serialLabel,
  statusClasses,
} from '../utils/drives'

function drive(over: Partial<DriveView> = {}): DriveView {
  return {
    id: 'drv_1',
    hostname: 'arm-ripper-abc',
    device_path: '/dev/sr0',
    display_name: null,
    status: 'online',
    last_seen_at: null,
    media_status: null,
    media_status_at: null,
    default_session_id: null,
    rip_speed: null,
    drive_mode: null,
    uhd_capable: null,
    prescan_cache_mb: null,
    prescan_timeout: null,
    prescan_retries: null,
    disc_enum_timeout: null,
    created_at: null,
    updated_at: null,
    lifecycle: 'enrolled',
    present: true,
    identity_kind: 'by_id',
    serial: 'AAAABBBB000E',
    by_id_name: 'usb-PIONEER_BD-RW_BDR-S12JX_AAAABBBB000E-0:0',
    vendor: 'PIONEER',
    model: 'BD-RW BDR-S12JX',
    last_error: null,
    current_job: null,
    ...over,
  }
}

describe('partitionDrives', () => {
  it('splits by lifecycle and keeps order within each bucket', () => {
    const p = partitionDrives([
      drive({ id: 'a', lifecycle: 'detected' }),
      drive({ id: 'b', lifecycle: 'enrolled' }),
      drive({ id: 'c', lifecycle: 'ignored' }),
      drive({ id: 'd', lifecycle: 'detected' }),
    ])
    expect(p.enrolled.map((d) => d.id)).toEqual(['b'])
    expect(p.detected.map((d) => d.id)).toEqual(['a', 'd'])
    expect(p.ignored.map((d) => d.id)).toEqual(['c'])
  })
})

describe('driveStatusLabel', () => {
  it('renders detached from the media status', () => {
    expect(
      driveStatusLabel(drive({ status: 'offline', media_status: 'detached', present: false })),
    ).toBe('○ detached — reconnect the drive')
  })
  it('renders detached from offline+absent even without a media status', () => {
    expect(driveStatusLabel(drive({ status: 'offline', present: false }))).toBe(
      '○ detached — reconnect the drive',
    )
  })
  it('keeps a plain offline (present, stale heartbeat) as offline', () => {
    expect(driveStatusLabel(drive({ status: 'offline', present: true }))).toBe('offline')
  })
  it('shows the error reason', () => {
    expect(
      driveStatusLabel(
        drive({ status: 'error', last_error: 'identity mismatch: row is bound to X' }),
      ),
    ).toBe('error: identity mismatch: row is bound to X')
    expect(driveStatusLabel(drive({ status: 'error' }))).toBe('error')
  })
  it('passes other statuses through', () => {
    expect(driveStatusLabel(drive({ status: 'ripping' }))).toBe('ripping')
  })
  it('prefers error over detached when both apply', () => {
    expect(
      driveStatusLabel(
        drive({
          status: 'error',
          media_status: 'detached',
          present: false,
          last_error: 'identity mismatch: x',
        }),
      ),
    ).toBe('error: identity mismatch: x')
  })
})

describe('statusClasses', () => {
  it('is badge+error for an error status', () => {
    expect(statusClasses(drive({ status: 'error', last_error: 'x' }))).toEqual(['badge', 'error'])
  })
  it('is badge+detached for a detached drive', () => {
    expect(
      statusClasses(drive({ status: 'offline', media_status: 'detached', present: false })),
    ).toEqual(['badge', 'detached'])
  })
  it('is plain badge otherwise', () => {
    expect(statusClasses(drive({ status: 'online' }))).toEqual(['badge'])
  })
})

describe('identityLine / serialLabel', () => {
  it('prefers display_name, then model, then hostname', () => {
    expect(identityLine(drive({ display_name: 'Living room' }))).toBe(
      'Living room · AAAABBBB000E · /dev/sr0',
    )
    expect(identityLine(drive())).toBe('BD-RW BDR-S12JX · AAAABBBB000E · /dev/sr0')
    expect(identityLine(drive({ model: null }))).toBe('arm-ripper-abc · AAAABBBB000E · /dev/sr0')
  })
  it('says no serial when there is none', () => {
    expect(identityLine(drive({ serial: null }))).toBe('BD-RW BDR-S12JX · no serial · /dev/sr0')
    expect(serialLabel(drive({ serial: null, identity_kind: 'port' }))).toEqual({
      text: 'no serial — identified by port',
      warn: true,
    })
    expect(serialLabel(drive())).toEqual({ text: 'AAAABBBB000E', warn: false })
  })
})

describe('isRipping', () => {
  it('is true for a ripping status or a ripping current job', () => {
    expect(isRipping(drive({ status: 'ripping' }))).toBe(true)
    expect(
      isRipping(
        drive({
          current_job: { id: 'job_1', title: null, status: 'ripping' },
        }),
      ),
    ).toBe(true)
    expect(isRipping(drive())).toBe(false)
  })
})
