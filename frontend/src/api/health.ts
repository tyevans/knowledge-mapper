import { apiClient } from './client'
import type { ApiResponse, HealthResponse } from './types'

/**
 * Health API endpoints
 */
export const healthApi = {
  /**
   * Check backend health status
   */
  async checkHealth(): Promise<ApiResponse<HealthResponse>> {
    return apiClient.get<HealthResponse>('/api/v1/health')
  },
}
