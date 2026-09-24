// Drive lifecycle endpoints (spec §6 "API client"). Every mutation's caller
// refetches listDrives() afterwards — unenroll may answer 204 with no body.
import { api } from './client'
import type { DriveRescanResponse, DriveView } from './types'

export function listDrives(): Promise<DriveView[]> {
  return api.get<DriveView[]>('/api/drives')
}

export function rescanDrives(): Promise<DriveRescanResponse> {
  return api.post<DriveRescanResponse>('/api/drives/rescan')
}

export function enrollDrive(id: string): Promise<DriveView> {
  return api.post<DriveView>(`/api/drives/${id}/enroll`)
}

export function ignoreDrive(id: string): Promise<DriveView> {
  return api.post<DriveView>(`/api/drives/${id}/ignore`)
}

export function unignoreDrive(id: string): Promise<DriveView> {
  return api.post<DriveView>(`/api/drives/${id}/unignore`)
}

export function unenrollDrive(id: string): Promise<void> {
  return api.postVoid(`/api/drives/${id}/unenroll`)
}
