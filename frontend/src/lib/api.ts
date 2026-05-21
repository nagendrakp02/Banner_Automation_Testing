import axios from 'axios'
import type { Banner, TestRun, CheckDef, HealthStatus } from '@/types'

const api = axios.create({ baseURL: '/api/v1' })

export const getBanners  = () => api.get<Banner[]>('/banners/').then(r => r.data)
export const createBanner = (d: Omit<Banner,'id'|'is_active'|'created_at'>) =>
  api.post<Banner>('/banners/', d).then(r => r.data)
export const updateBanner = (id: string, d: Partial<Banner>) =>
  api.patch<Banner>(`/banners/${id}`, d).then(r => r.data)
export const deleteBanner = (id: string) => api.delete(`/banners/${id}`)

export const getRuns   = (bannerId?: string) =>
  api.get<TestRun[]>('/runs/', { params: bannerId ? { banner_id: bannerId } : {} }).then(r => r.data)
export const getRun    = (id: string) => api.get<TestRun>(`/runs/${id}`).then(r => r.data)
export const createRun = (bannerId: string, checkIds: string[]) =>
  api.post<TestRun>('/runs/', { banner_id: bannerId, check_ids: checkIds }).then(r => r.data)
export const deleteRun = (id: string) => api.delete(`/runs/${id}`)

export const getChecks = () => api.get<CheckDef[]>('/checks').then(r => r.data)
export const getHealth = () => api.get<HealthStatus>('/health').then(r => r.data)
