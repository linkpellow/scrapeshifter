/**
 * Scrapegoat API Client
 * Typed fetch wrapper for communicating with the Scrapegoat enrichment service
 */

// Types for Scrapegoat API responses
export interface HealthResponse {
  status: 'healthy' | 'degraded';
  redis: 'connected' | 'disconnected';
  redis_url_configured: boolean;
  error?: string | null;
}

export interface QueueStatusResponse {
  leads_to_enrich: number;
  failed_leads: number;
  status: 'active' | 'inactive';
}

export interface PipelineStatus {
  health: HealthResponse;
  queue: QueueStatusResponse;
  timestamp: string;
}

export interface DLQItem {
  index: number;
  lead_data: {
    linkedinUrl?: string;
    name?: string;
    location?: string;
    [key: string]: any;
  };
  error: string;
  retry_count: number;
  failed_at: string;
}

export interface DLQListResponse {
  failed_leads: DLQItem[];
  total: number;
}

export interface DLQRetryResponse {
  success: boolean;
  message: string;
  retried_count?: number;
}

/** Scrapegoat base URL for all BrainScraper→Scrapegoat calls. SCRAPEGOAT_API_URL or SCRAPEGOAT_URL. */
export function getScrapegoatBase(): string {
  const url = process.env.SCRAPEGOAT_API_URL || process.env.SCRAPEGOAT_URL;
  if (!url) {
    console.warn('SCRAPEGOAT_API_URL / SCRAPEGOAT_URL not set, using default');
    return 'https://scrapegoat-production-8d0a.up.railway.app';
  }
  return url.replace(/\/$/, '');
}

class ScrapegoatClient {
  private baseUrl: string;
  private timeout: number;

  constructor() {
    this.baseUrl = getScrapegoatBase();
    this.timeout = 10000; // 10 second timeout
  }

  private async fetch<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        ...options,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Scrapegoat API error (${response.status}): ${errorText}`);
      }

      return await response.json();
    } catch (error) {
      clearTimeout(timeoutId);
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error('Scrapegoat API request timed out');
      }
      throw error;
    }
  }

  /**
   * Get health status of Scrapegoat service
   */
  async getHealth(): Promise<HealthResponse> {
    return this.fetch<HealthResponse>('/health');
  }

  /**
   * Get queue status (pending leads, failed leads count)
   */
  async getQueueStatus(): Promise<QueueStatusResponse> {
    return this.fetch<QueueStatusResponse>('/queue/status');
  }

  /**
   * Get combined pipeline status (health + queue).
   * Normalizes Scrapegoat /health (which returns {status, service, timestamp}) into
   * HealthResponse {status, redis, redis_url_configured} for UI compatibility.
   */
  async getPipelineStatus(): Promise<PipelineStatus> {
    const [health, queue] = await Promise.all([
      this.getHealth().catch((e) => ({
        status: 'degraded' as const,
        redis: 'disconnected' as const,
        redis_url_configured: false,
        error: e.message,
      })),
      this.getQueueStatus().catch(() => ({
        leads_to_enrich: 0,
        failed_leads: 0,
        status: 'inactive' as const,
      })),
    ]);

    // Normalize: Scrapegoat /health is minimal; ensure HealthResponse shape.
    // Use queue.status === 'active' to infer Redis (successful /queue/status); catch gives 'inactive'.
    const h = health as HealthResponse & { service?: string; redis?: string; redis_url_configured?: boolean };
    if (h.redis === undefined) {
      h.redis = queue && (queue as { status?: string }).status === 'active' ? 'connected' : 'disconnected';
      h.redis_url_configured = h.redis === 'connected';
    }

    return {
      health: h,
      queue,
      timestamp: new Date().toISOString(),
    };
  }

  /**
   * Get list of failed leads from DLQ
   */
  async getDLQ(limit?: number): Promise<DLQListResponse> {
    const endpoint = limit ? `/dlq?limit=${limit}` : '/dlq';
    return this.fetch<DLQListResponse>(endpoint);
  }

  /**
   * Retry a single failed lead by index
   */
  async retryOne(index: number): Promise<DLQRetryResponse> {
    return this.fetch<DLQRetryResponse>(`/dlq/retry/${index}`, {
      method: 'POST',
    });
  }

  /**
   * Retry all failed leads
   */
  async retryAll(): Promise<DLQRetryResponse> {
    return this.fetch<DLQRetryResponse>('/dlq/retry-all', {
      method: 'POST',
    });
  }
}

// Export singleton instance
export const scrapegoatClient = new ScrapegoatClient();

// Export types for use in components
export type { ScrapegoatClient };
