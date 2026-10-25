// API Client - TypeScript
const API_BASE = import.meta.env?.VITE_API_BASE || window.location.origin;

interface ApiResponse<T> {
  ok: boolean;
  data?: T;
  error?: string;
}

class ApiClient {
  private token: string | null = null;

  setToken(token: string): void {
    this.token = token;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string>),
    };

    if (this.token) {
      headers["X-API-Key"] = this.token;
    }

    try {
      const res = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers,
      });

      const data = await res.json();

      if (!res.ok) {
        return {
          ok: false,
          error: data.error || data.detail || `HTTP ${res.status}`,
        };
      }

      return { ok: true, data: data as T };
    } catch (err: any) {
      return {
        ok: false,
        error: err.message || "Network error",
      };
    }
  }

  // Auth
  async telegramAuth(initData: string): Promise<ApiResponse<any>> {
    return this.request("/v1/web/auth/telegram", {
      method: "POST",
      body: JSON.stringify({ init_data: initData }),
    });
  }

  // Keys
  async createKey(body: {
    tier: string;
    label?: string;
    scopes?: string[];
    expires_in_days?: number;
  }): Promise<ApiResponse<any>> {
    return this.request("/v1/web/keys/create", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  async listKeys(): Promise<ApiResponse<any>> {
    return this.request("/v1/web/keys/list");
  }

  async getKey(keyId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/web/keys/${key_id}`);
  }

  async revokeKey(keyId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/web/keys/${key_id}`, {
      method: "DELETE",
    });
  }

  async patchKey(keyId: string, body: any): Promise<ApiResponse<any>> {
    return this.request(`/v1/web/keys/${key_id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  }

  async rotateKey(keyId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/web/keys/${key_id}`, {
      method: "PATCH",
      body: JSON.stringify({ action: "rotate" }),
    });
  }

  // Stats
  async getStats(): Promise<ApiResponse<any>> {
    return this.request("/v1/web/stats");
  }

  // Owner routes
  async ownerKeys(): Promise<ApiResponse<any>> {
    return this.request("/v1/web/owner/keys");
  }

  // Music
  async searchMusic(query: string, source?: string, limit?: number): Promise<ApiResponse<any>> {
    const params = new URLSearchParams({ q: query });
    if (source) params.set("source", source);
    if (limit) params.set("limit", String(limit));
    return this.request(`/v1/search?${params}`);
  }

  async getTrackInfo(url: string, source?: string): Promise<ApiResponse<any>> {
    const params = new URLSearchParams({ url });
    if (source) params.set("source", source);
    return this.request(`/v1/info?${params}`);
  }

  async getLyrics(url: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/lyrics?url=${encodeURIComponent(url)}`);
  }

  async downloadTrack(url: string, source?: string): Promise<ApiResponse<any>> {
    return this.request("/v1/download", {
      method: "POST",
      body: JSON.stringify({ url, source }),
    });
  }

  // Anime
  async searchAnime(query: string, source?: string): Promise<ApiResponse<any>> {
    const params = new URLSearchParams({ q: query });
    if (source) params.set("source", source);
    return this.request(`/v1/anime/search?${params}`);
  }

  async getAnimeInfo(url: string, source?: string): Promise<ApiResponse<any>> {
    const params = new URLSearchParams({ url });
    if (source) params.set("source", source);
    return this.request(`/v1/anime/info?${params}`);
  }

  async downloadAnime(url: string, source?: string): Promise<ApiResponse<any>> {
    return this.request("/v1/anime/download", {
      method: "POST",
      body: JSON.stringify({ url, source }),
    });
  }

  // Manga
  async searchManga(query: string, source?: string): Promise<ApiResponse<any>> {
    const params = new URLSearchParams({ q: query });
    if (source) params.set("source", source);
    return this.request(`/v1/manga/search?${params}`);
  }

  async getMangaInfo(url: string, source?: string): Promise<ApiResponse<any>> {
    const params = new URLSearchParams({ url });
    if (source) params.set("source", source);
    return this.request(`/v1/manga/info?${params}`);
  }

  async downloadManga(url: string, source?: string): Promise<ApiResponse<any>> {
    return this.request("/v1/manga/download", {
      method: "POST",
      body: JSON.stringify({ url, source }),
    });
  }

  // M3U8/HLS/DASH
  async parseM3u8(url: string): Promise<ApiResponse<any>> {
    return this.request("/v1/m3u8/parse", {
      method: "POST",
      body: JSON.stringify({ url }),
    });
  }

  async downloadM3u8(url: string): Promise<ApiResponse<any>> {
    return this.request("/v1/m3u8/download", {
      method: "POST",
      body: JSON.stringify({ url }),
    });
  }

  // Sources
  async getSources(): Promise<ApiResponse<any>> {
    return this.request("/v1/sources");
  }

  // Health
  async health(): Promise<ApiResponse<any>> {
    return this.request("/health");
  }
}

export const api = new ApiClient();
export type { ApiResponse };
