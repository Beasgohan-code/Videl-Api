/**
 * API Client - TypeScript
 * Full-featured client for Videl-Api with all 222+ endpoints
 */

const API_BASE = import.meta.env?.VITE_API_BASE || window.location.origin;

interface ApiResponse<T> {
  ok: boolean;
  data?: T;
  error?: string;
}

class ApiClient {
  private token: string | null = null;
  private ws: WebSocket | null = null;
  private wsListeners: Map<string, Function[]> = new Map();
  private wsReconnectAttempts = 0;
  private wsMaxReconnects = 5;

  setToken(token: string): void {
    this.token = token;
  }

  clearToken(): void {
    this.token = null;
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

  // ---------- Auth ----------
  async telegramAuth(initData: string): Promise<ApiResponse<any>> {
    return this.request("/v1/web/auth/telegram", {
      method: "POST",
      body: JSON.stringify({ init_data: initData }),
    });
  }

  async oauthToken(clientId: string, clientSecret: string, scope?: string): Promise<ApiResponse<any>> {
    return this.request("/v1/auth/token", {
      method: "POST",
      body: JSON.stringify({ client_id: clientId, client_secret: clientSecret, scope }),
    });
  }

  async twoFactorSetup(userId: number): Promise<ApiResponse<any>> {
    return this.request("/v1/auth/2fa/setup", {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    });
  }

  async twoFactorVerify(userId: number, token: string): Promise<ApiResponse<any>> {
    return this.request("/v1/auth/2fa/verify", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, token }),
    });
  }

  async passwordResetRequest(email: string): Promise<ApiResponse<any>> {
    return this.request("/v1/auth/password-reset/request", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
  }

  async passwordResetConfirm(token: string, newPassword: string): Promise<ApiResponse<any>> {
    return this.request("/v1/auth/password-reset/confirm", {
      method: "POST",
      body: JSON.stringify({ token, new_password: newPassword }),
    });
  }

  // ---------- Keys ----------
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
    return this.request(`/v1/web/keys/${keyId}`);
  }

  async revokeKey(keyId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/web/keys/${keyId}`, { method: "DELETE" });
  }

  async patchKey(keyId: string, body: any): Promise<ApiResponse<any>> {
    return this.request(`/v1/web/keys/${keyId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  }

  async rotateKey(keyId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/web/keys/${keyId}`, {
      method: "PATCH",
      body: JSON.stringify({ action: "rotate" }),
    });
  }

  async setKeyScopes(keyId: string, scopes: string[]): Promise<ApiResponse<any>> {
    return this.request(`/v1/keys/${keyId}/scopes`, {
      method: "POST",
      body: JSON.stringify({ scopes }),
    });
  }

  async setKeyConcurrency(keyId: string, maxConcurrent: number): Promise<ApiResponse<any>> {
    return this.request(`/v1/keys/${keyId}/concurrency`, {
      method: "POST",
      body: JSON.stringify({ max_concurrent: maxConcurrent }),
    });
  }

  async setKeyFileFilter(keyId: string, allowed: string[], blocked: string[]): Promise<ApiResponse<any>> {
    return this.request(`/v1/keys/${keyId}/file-type-filter`, {
      method: "POST",
      body: JSON.stringify({ allowed_extensions: allowed, blocked_extensions: blocked }),
    });
  }

  async getKeyUsage(keyId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/keys/${keyId}/usage`);
  }

  async getKeyConcurrency(keyId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/keys/${keyId}/concurrency`);
  }

  async getKeyRateLimit(keyId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/keys/${keyId}/rate-limit`);
  }

  async shareKey(keyId: string, expiresInHours: number, maxUses?: number): Promise<ApiResponse<any>> {
    return this.request("/v1/keys/share", {
      method: "POST",
      body: JSON.stringify({ key_id: keyId, expires_in_hours: expiresInHours, max_uses: maxUses }),
    });
  }

  async listKeyShares(): Promise<ApiResponse<any>> {
    return this.request("/v1/keys/shares");
  }

  async scheduleKeyRotation(keyId: string, intervalDays: number, enabled: boolean): Promise<ApiResponse<any>> {
    return this.request("/v1/keys/rotation/schedule", {
      method: "POST",
      body: JSON.stringify({ key_id: keyId, interval_days: intervalDays, enabled }),
    });
  }

  async listKeyRotations(): Promise<ApiResponse<any>> {
    return this.request("/v1/keys/rotation");
  }

  async bulkCreateKeys(count: number, tier: string, scopes: string[]): Promise<ApiResponse<any>> {
    return this.request("/v1/keys/bulk", {
      method: "POST",
      body: JSON.stringify({ count, tier, scopes }),
    });
  }

  // ---------- Users ----------
  async createUser(body: {
    telegram_id?: number;
    username?: string;
    first_name?: string;
    tier?: string;
  }): Promise<ApiResponse<any>> {
    return this.request("/v1/users", { method: "POST", body: JSON.stringify(body) });
  }

  async listUsers(limit?: number, offset?: number): Promise<ApiResponse<any>> {
    const params = new URLSearchParams();
    if (limit) params.set("limit", String(limit));
    if (offset) params.set("offset", String(offset));
    return this.request(`/v1/users?${params}`);
  }

  async getUser(userId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/users/${userId}`);
  }

  async updateUser(userId: string, body: any): Promise<ApiResponse<any>> {
    return this.request(`/v1/users/${userId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  }

  async deleteUser(userId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/users/${userId}`, { method: "DELETE" });
  }

  async setUserTier(userId: string, tier: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/users/${userId}/tier`, {
      method: "POST",
      body: JSON.stringify({ tier }),
    });
  }

  // ---------- Tiers ----------
  async listTiers(): Promise<ApiResponse<any>> {
    return this.request("/v1/tiers");
  }

  async setTierFeature(tier: string, feature: string, enabled: boolean): Promise<ApiResponse<any>> {
    return this.request("/v1/tiers/features", {
      method: "POST",
      body: JSON.stringify({ tier, feature, enabled }),
    });
  }

  async getTierFeatures(tier: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/tiers/${tier}/features`);
  }

  // ---------- Search ----------
  async searchMusic(query: string, source?: string, limit?: number): Promise<ApiResponse<any>> {
    const params = new URLSearchParams({ q: query });
    if (source) params.set("source", source);
    if (limit) params.set("limit", String(limit));
    return this.request(`/v1/search?${params}`);
  }

  async federatedSearch(query: string, limit?: number, source?: string): Promise<ApiResponse<any>> {
    const params = new URLSearchParams({ q: query, limit: String(limit || 10) });
    if (source) params.set("source", source);
    return this.request(`/v1/federated-search?${params}`);
  }

  async searchHistory(limit?: number): Promise<ApiResponse<any>> {
    const params = new URLSearchParams();
    if (limit) params.set("limit", String(limit));
    return this.request(`/v1/search/history?${params}`);
  }

  async recordSearchHistory(query: string, source?: string, resultsCount?: number): Promise<ApiResponse<any>> {
    return this.request("/v1/search/history", {
      method: "POST",
      body: JSON.stringify({ query, source, results_count: resultsCount }),
    });
  }

  async savedSearches(): Promise<ApiResponse<any>> {
    return this.request("/v1/search/saved");
  }

  async createSavedSearch(name: string, query: string, source?: string): Promise<ApiResponse<any>> {
    return this.request("/v1/search/saved", {
      method: "POST",
      body: JSON.stringify({ name, query, source }),
    });
  }

  async deleteSavedSearch(searchId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/search/saved/${searchId}`, { method: "DELETE" });
  }

  async autocomplete(query: string, source?: string, limit?: number): Promise<ApiResponse<any>> {
    return this.request("/v1/search/autocomplete", {
      method: "POST",
      body: JSON.stringify({ query, source, limit }),
    });
  }

  async trending(limit?: number): Promise<ApiResponse<any>> {
    const params = new URLSearchParams();
    if (limit) params.set("limit", String(limit));
    return this.request(`/v1/search/trending?${params}`);
  }

  async getSources(): Promise<ApiResponse<any>> {
    return this.request("/v1/sources");
  }

  // ---------- Info / Lyrics / Metadata ----------
  async getTrackInfo(url: string, source?: string): Promise<ApiResponse<any>> {
    const params = new URLSearchParams({ url });
    if (source) params.set("source", source);
    return this.request(`/v1/info?${params}`);
  }

  async getLyrics(url: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/lyrics?url=${encodeURIComponent(url)}`);
  }

  async getMetadata(url?: string, query?: string): Promise<ApiResponse<any>> {
    const params = new URLSearchParams();
    if (url) params.set("url", url);
    if (query) params.set("query", query);
    return this.request(`/v1/metadata?${params}`);
  }

  async rateContent(contentId: string, rating: number, review?: string): Promise<ApiResponse<any>> {
    return this.request("/v1/content/rate", {
      method: "POST",
      body: JSON.stringify({ content_id: contentId, rating, review }),
    });
  }

  async getContentRating(contentId: string, userId?: number): Promise<ApiResponse<any>> {
    const params = new URLSearchParams({ content_id: contentId });
    if (userId) params.set("user_id", String(userId));
    return this.request(`/v1/content/rate/${contentId}?${params}`);
  }

  // ---------- Download ----------
  async downloadTrack(url: string, source?: string, body?: any): Promise<ApiResponse<any>> {
    return this.request("/v1/download", {
      method: "POST",
      body: JSON.stringify({ url, source, ...body }),
    });
  }

  async createAdvancedDownload(body: {
    url: string;
    source?: string;
    user_id?: number;
    priority?: "high" | "normal" | "low";
    format?: string;
    quality?: string;
    use_aria2c?: boolean;
    embed_metadata?: boolean;
    fetch_lyrics?: boolean;
    cookies?: string;
    cookies_file?: string;
    proxy?: string;
    user_agent?: string;
    referer?: string;
    max_filesize?: number;
    skip_download?: boolean;
  }): Promise<ApiResponse<any>> {
    return this.request("/v1/download/advanced", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  async listAdvancedDownloads(userId?: number): Promise<ApiResponse<any>> {
    const params = new URLSearchParams();
    if (userId) params.set("user_id", String(userId));
    return this.request(`/v1/download/advanced?${params}`);
  }

  async getDownloadStatus(jobId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/download/advanced/status/${jobId}`);
  }

  async pauseDownload(jobId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/download/advanced/pause/${jobId}`, { method: "POST" });
  }

  async resumeDownload(jobId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/download/advanced/resume/${jobId}`, { method: "POST" });
  }

  async cancelDownload(jobId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/download/advanced/cancel/${jobId}`, { method: "POST" });
  }

  async setSpeedLimit(keyId: string, maxKbps: number): Promise<ApiResponse<any>> {
    return this.request("/v1/download/speed-limit", {
      method: "POST",
      body: JSON.stringify({ key_id: keyId, max_kbps: maxKbps }),
    });
  }

  async setBandwidthAllocation(keyId: string, maxBytesPerDay: number, maxBytesPerMonth: number): Promise<ApiResponse<any>> {
    return this.request("/v1/download/bandwidth", {
      method: "POST",
      body: JSON.stringify({ key_id: keyId, max_bytes_per_day: maxBytesPerDay, max_bytes_per_month: maxBytesPerMonth }),
    });
  }

  async setDownloadNotification(jobId: string, notifyComplete: boolean, notifyError: boolean, channels: string[]): Promise<ApiResponse<any>> {
    return this.request("/v1/download/notify", {
      method: "POST",
      body: JSON.stringify({ job_id: jobId, notify_on_complete: notifyComplete, notify_on_error: notifyError, channels }),
    });
  }

  async setRetryPolicy(maxRetries: number, backoffSeconds: number, retryOnError: boolean): Promise<ApiResponse<any>> {
    return this.request("/v1/download/retry-policy", {
      method: "POST",
      body: JSON.stringify({ max_retries: maxRetries, backoff_seconds: backoffSeconds, retry_on_error: retryOnError }),
    });
  }

  async createDownloadSchedule(url: string, cronExpression: string, enabled?: boolean, format?: string, source?: string): Promise<ApiResponse<any>> {
    return this.request("/v1/download/schedule", {
      method: "POST",
      body: JSON.stringify({ url, cron_expression: cronExpression, enabled, format, source }),
    });
  }

  async listDownloadSchedules(): Promise<ApiResponse<any>> {
    return this.request("/v1/download/schedule");
  }

  async toggleDownloadSchedule(scheduleId: string, enabled: boolean): Promise<ApiResponse<any>> {
    return this.request(`/v1/download/schedule/${scheduleId}/toggle`, {
      method: "POST",
      body: JSON.stringify({ enabled }),
    });
  }

  // ---------- Favorites ----------
  async addFavorite(body: {
    title: string;
    url: string;
    source?: string;
    thumbnail?: string;
    tags?: string[];
  }): Promise<ApiResponse<any>> {
    return this.request("/v1/favorites", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  async listFavorites(): Promise<ApiResponse<any>> {
    return this.request("/v1/favorites");
  }

  async removeFavorite(favId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/favorites/${favId}`, { method: "DELETE" });
  }

  // ---------- Playlists ----------
  async createPlaylist(body: {
    name: string;
    description?: string;
    is_public?: boolean;
  }): Promise<ApiResponse<any>> {
    return this.request("/v1/playlists", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  async listPlaylists(): Promise<ApiResponse<any>> {
    return this.request("/v1/playlists");
  }

  async getPlaylist(playlistId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/playlists/${playlistId}`);
  }

  async updatePlaylist(playlistId: string, body: any): Promise<ApiResponse<any>> {
    return this.request(`/v1/playlists/${playlistId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  }

  async deletePlaylist(playlistId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/playlists/${playlistId}`, { method: "DELETE" });
  }

  async addPlaylistItem(playlistId: string, body: {
    title: string;
    url: string;
    source?: string;
    duration?: number;
    thumbnail?: string;
  }): Promise<ApiResponse<any>> {
    return this.request(`/v1/playlists/${playlistId}/items`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  async removePlaylistItem(playlistId: string, itemId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/playlists/${playlistId}/items/${itemId}`, {
      method: "DELETE",
    });
  }

  // ---------- M3U8/HLS/DASH ----------
  async parseM3u8(url: string, headers?: any, cookies?: string, proxy?: string): Promise<ApiResponse<any>> {
    return this.request("/v1/m3u8/parse", {
      method: "POST",
      body: JSON.stringify({ url, headers, cookies, proxy }),
    });
  }

  async downloadM3u8(url: string, body?: any): Promise<ApiResponse<any>> {
    return this.request("/v1/m3u8/download", {
      method: "POST",
      body: JSON.stringify({ url, ...body }),
    });
  }

  // ---------- Stats / Analytics ----------
  async getStats(): Promise<ApiResponse<any>> {
    return this.request("/v1/web/stats");
  }

  async getGlobalStats(): Promise<ApiResponse<any>> {
    return this.request("/v1/stats/global");
  }

  async getUsageStats(): Promise<ApiResponse<any>> {
    return this.request("/v1/stats/usage");
  }

  async getSourceStats(): Promise<ApiSourceStats[]> {
    const res = await this.request("/v1/stats/sources");
    return res.ok ? (res.data as any) || [] : [];
  }

  async getActivityFeed(limit?: number): Promise<ApiResponse<any>> {
    const params = new URLSearchParams();
    if (limit) params.set("limit", String(limit));
    return this.request(`/v1/activity/feed?${params}`);
  }

  async recordActivity(action: string, details?: any): Promise<ApiResponse<any>> {
    return this.request("/v1/activity/record", {
      method: "POST",
      body: JSON.stringify({ action, details }),
    });
  }

  // ---------- Notifications ----------
  async listNotifications(unreadOnly?: boolean): Promise<ApiResponse<any>> {
    const params = new URLSearchParams();
    if (unreadOnly) params.set("unread_only", "true");
    return this.request(`/v1/notifications?${params}`);
  }

  async createNotification(title: string, message: string, type: string = "info"): Promise<ApiResponse<any>> {
    return this.request("/v1/notifications", {
      method: "POST",
      body: JSON.stringify({ title, message, type }),
    });
  }

  async markNotificationRead(notifId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/notifications/${notifId}/read`, { method: "PUT" });
  }

  async getNotificationPrefs(): Promise<ApiResponse<any>> {
    return this.request("/v1/notifications/preferences");
  }

  async setNotificationPrefs(prefs: any): Promise<ApiResponse<any>> {
    return this.request("/v1/notifications/preferences", {
      method: "PUT",
      body: JSON.stringify(prefs),
    });
  }

  // ---------- Payments ----------
  async createInvoice(title: string, description: string, amount: number, currency: string = "XTR"): Promise<ApiResponse<any>> {
    return this.request("/v1/payments/invoice", {
      method: "POST",
      body: JSON.stringify({ title, description, amount, currency }),
    });
  }

  async paymentHistory(): Promise<ApiResponse<any>> {
    return this.request("/v1/payments/history");
  }

  // ---------- Webhooks ----------
  async listWebhooks(): Promise<ApiResponse<any>> {
    return this.request("/v1/webhooks");
  }

  async createWebhook(url: string, events: string[], secret?: string): Promise<ApiResponse<any>> {
    return this.request("/v1/webhooks", {
      method: "POST",
      body: JSON.stringify({ url, events, secret }),
    });
  }

  async deleteWebhook(webhookId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/webhooks/${webhookId}`, { method: "DELETE" });
  }

  // ---------- Cache ----------
  async getCacheStats(): Promise<ApiResponse<any>> {
    return this.request("/v1/cache/stats");
  }

  async clearCache(): Promise<ApiResponse<any>> {
    return this.request("/v1/cache/clear", { method: "POST" });
  }

  async invalidateCacheTag(tag: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/cache/invalidate/${tag}`, { method: "POST" });
  }

  async warmCache(queries: string[], source: string, limitPerQuery: number): Promise<ApiResponse<any>> {
    return this.request("/v1/cache/warm", {
      method: "POST",
      body: JSON.stringify({ queries, source, limit_per_query: limitPerQuery }),
    });
  }

  // ---------- Scheduler ----------
  async listSchedulerTasks(): Promise<ApiResponse<any>> {
    return this.request("/v1/scheduler/tasks");
  }

  async enableSchedulerTask(name: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/scheduler/tasks/${name}/enable`, { method: "POST" });
  }

  async disableSchedulerTask(name: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/scheduler/tasks/${name}/disable`, { method: "POST" });
  }

  // ---------- Plugins ----------
  async listPlugins(): Promise<ApiResponse<any>> {
    return this.request("/v1/plugins");
  }

  async enablePlugin(pluginId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/plugins/${pluginId}/enable`, { method: "POST" });
  }

  async disablePlugin(pluginId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/plugins/${pluginId}/disable`, { method: "POST" });
  }

  // ---------- System ----------
  async getSystemInfo(): Promise<ApiResponse<any>> {
    return this.request("/v1/system/info");
  }

  async getSystemDisk(): Promise<ApiResponse<any>> {
    return this.request("/v1/system/disk");
  }

  async getSystemMemory(): Promise<ApiResponse<any>> {
    return this.request("/v1/system/memory");
  }

  async getConfig(): Promise<ApiResponse<any>> {
    return this.request("/v1/config");
  }

  async getVersion(): Promise<ApiResponse<any>> {
    return this.request("/v1/version");
  }

  async getMaintenance(): Promise<ApiResponse<any>> {
    return this.request("/v1/maintenance");
  }

  // ---------- Geo / IP ----------
  async geoCheck(countryCode: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/geo/check/${countryCode}`);
  }

  async listGeoBlocks(): Promise<ApiResponse<any>> {
    return this.request("/v1/geo/blocked");
  }

  async getIpReputation(ip: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/ip/reputation/${ip}`);
  }

  // ---------- Sessions ----------
  async listSessions(): Promise<ApiResponse<any>> {
    return this.request("/v1/sessions");
  }

  async revokeSession(sessionId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/sessions/${sessionId}`, { method: "DELETE" });
  }

  // ---------- Teams ----------
  async listTeams(): Promise<ApiResponse<any>> {
    return this.request("/v1/teams");
  }

  async createTeam(name: string): Promise<ApiResponse<any>> {
    return this.request("/v1/teams", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
  }

  // ---------- Export ----------
  async exportHistory(format: string = "json"): Promise<ApiResponse<any>> {
    return this.request("/v1/export/history", {
      method: "POST",
      body: JSON.stringify({ format }),
    });
  }

  async listExports(): Promise<ApiResponse<any>> {
    return this.request("/v1/export/history");
  }

  // ---------- Files ----------
  async listFiles(): Promise<ApiResponse<any>> {
    return this.request("/v1/files");
  }

  async deleteFile(folder: string, filename: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/files/${folder}/${filename}`, { method: "DELETE" });
  }

  // ---------- Reports ----------
  async createUsageReport(period: string = "monthly", format: string = "csv"): Promise<ApiResponse<any>> {
    return this.request("/v1/reports/usage", {
      method: "POST",
      body: JSON.stringify({ period, format }),
    });
  }

  async listUsageReports(): Promise<ApiResponse<any>> {
    return this.request("/v1/reports/usage");
  }

  // ---------- Suspicious Activity ----------
  async listSuspiciousActivity(limit?: number): Promise<ApiResponse<any>> {
    const params = new URLSearchParams();
    if (limit) params.set("limit", String(limit));
    return this.request(`/v1/suspicious-activity?${params}`);
  }

  // ---------- Moderation ----------
  async listModeration(status?: string): Promise<ApiResponse<any>> {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    return this.request(`/v1/moderation?${params}`);
  }

  // ---------- WebSocket ----------
  wsConnect(userId: number): void {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/v1/ws/${userId}`;

    try {
      this.ws = new WebSocket(wsUrl);
      this.ws.onopen = () => {
        this.wsReconnectAttempts = 0;
        this.emit("ws:open", {});
      };
      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.emit("ws:message", data);
          this.emit(`ws:${data.type}`, data);
        } catch {}
      };
      this.ws.onclose = () => {
        this.ws = null;
        this.emit("ws:close", {});
        if (this.wsReconnectAttempts < this.wsMaxReconnects) {
          this.wsReconnectAttempts++;
          setTimeout(() => this.wsConnect(userId), 3000 * this.wsReconnectAttempts);
        }
      };
      this.ws.onerror = () => {
        this.ws?.close();
      };
    } catch {}
  }

  wsDisconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  wsSubscribe(channel: string): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: "subscribe", channel }));
    }
  }

  wsUnsubscribe(channel: string): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: "unsubscribe", channel }));
    }
  }

  wsPing(timestamp: number): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: "ping", timestamp }));
    }
  }

  on(event: string, callback: Function): void {
    if (!this.wsListeners.has(event)) {
      this.wsListeners.set(event, []);
    }
    this.wsListeners.get(event)!.push(callback);
  }

  off(event: string, callback: Function): void {
    const listeners = this.wsListeners.get(event);
    if (listeners) {
      const idx = listeners.indexOf(callback);
      if (idx >= 0) listeners.splice(idx, 1);
    }
  }

  private emit(event: string, data: any): void {
    const listeners = this.wsListeners.get(event);
    if (listeners) {
      listeners.forEach((cb) => cb(data));
    }
  }

  getWsConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

export const api = new ApiClient();
export type { ApiResponse };

interface ApiSourceStats {
  source_id: string;
  source_name: string;
  searches: number;
  downloads: number;
  errors: number;
}
