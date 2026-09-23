import { hostApi } from './client'
import type { ApiResult } from '../../types'

/** A user as the backend reports them 鈥?mirrors the `users` table row. */
export interface AuthUserDto {
  id: number
  username: string
  role: string
  workspace?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface LoginResponseDto {
  token: string
  /** Epoch milliseconds. */
  expires_at: number
  user: AuthUserDto
}

export const authApi = {
  login(username: string, password: string): Promise<ApiResult<LoginResponseDto>> {
    return hostApi.post<LoginResponseDto>('/auth/login', { username, password })
  },

  /** Who the stored token belongs to; also the check that it is still valid. */
  me(): Promise<ApiResult<AuthUserDto>> {
    return hostApi.get<AuthUserDto>('/auth/me')
  },
}
