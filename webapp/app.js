/**
 * Telegram WebApp SDK wrapper - TypeScript
 * Provides type-safe access to Telegram WebApp features
 */
const tg = window.Telegram?.WebApp || window.tg?.WebApp;
{ tg };
function getInitData() {
    return tg?.initData || "";
}
function getTelegramUser() {
    return tg?.initDataUnsafe?.user || null;
}
function isTelegramWebApp() {
    return !!tg;
}
function getThemeParams() {
    return tg?.themeParams || {};
}
function initWebApp() {
    if (tg) {
        tg.ready();
        tg.expand();
        tg.MainButton.setText("Create API Key");
        tg.MainButton.show();
        tg.SecondaryButton.hide();
        tg.BackButton.hide();
    }
}
function haptic(type) {
    if (!tg)
        return;
    try {
        if (type === "success")
            tg.HapticFeedback.notificationOccurred("success");
        else if (type === "error")
            tg.HapticFeedback.notificationOccurred("error");
        else if (type === "warning")
            tg.HapticFeedback.notificationOccurred("warning");
        else if (type === "selection")
            tg.HapticFeedback.selectionChanged();
        else
            tg.HapticFeedback.impactOccurred(type);
    }
    catch { }
}
function showAlert(message) {
    tg?.showAlert(message);
}
function showConfirm(message, callback) {
    tg?.showConfirm(message, callback);
}
function showPopup(params, callback) {
    tg?.showPopup(params, callback);
}
/**
 * API Client - TypeScript
 * Full-featured client for Videl-Api with all 222+ endpoints
 */
const API_BASE = window.location.origin;
class ApiClient {
    constructor() {
        this.token = null;
        this.ws = null;
        this.wsListeners = new Map();
        this.wsReconnectAttempts = 0;
        this.wsMaxReconnects = 5;
    }
    setToken(token) {
        this.token = token;
    }
    clearToken() {
        this.token = null;
    }
    async request(endpoint, options = {}) {
        const headers = {
            "Content-Type": "application/json",
            ...options.headers,
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
            return { ok: true, data: data };
        }
        catch (err) {
            return {
                ok: false,
                error: err.message || "Network error",
            };
        }
    }
    // ---------- Auth ----------
    async telegramAuth(initData) {
        return this.request("/v1/web/auth/telegram", {
            method: "POST",
            body: JSON.stringify({ init_data: initData }),
        });
    }
    async oauthToken(clientId, clientSecret, scope) {
        return this.request("/v1/auth/token", {
            method: "POST",
            body: JSON.stringify({ client_id: clientId, client_secret: clientSecret, scope }),
        });
    }
    async twoFactorSetup(userId) {
        return this.request("/v1/auth/2fa/setup", {
            method: "POST",
            body: JSON.stringify({ user_id: userId }),
        });
    }
    async twoFactorVerify(userId, token) {
        return this.request("/v1/auth/2fa/verify", {
            method: "POST",
            body: JSON.stringify({ user_id: userId, token }),
        });
    }
    async passwordResetRequest(email) {
        return this.request("/v1/auth/password-reset/request", {
            method: "POST",
            body: JSON.stringify({ email }),
        });
    }
    async passwordResetConfirm(token, newPassword) {
        return this.request("/v1/auth/password-reset/confirm", {
            method: "POST",
            body: JSON.stringify({ token, new_password: newPassword }),
        });
    }
    // ---------- Keys ----------
    async createKey(body) {
        return this.request("/v1/web/keys/create", {
            method: "POST",
            body: JSON.stringify(body),
        });
    }
    async listKeys() {
        return this.request("/v1/web/keys/list");
    }
    async getKey(keyId) {
        return this.request(`/v1/web/keys/${keyId}`);
    }
    async revokeKey(keyId) {
        return this.request(`/v1/web/keys/${keyId}`, { method: "DELETE" });
    }
    async patchKey(keyId, body) {
        return this.request(`/v1/web/keys/${keyId}`, {
            method: "PATCH",
            body: JSON.stringify(body),
        });
    }
    async rotateKey(keyId) {
        return this.request(`/v1/web/keys/${keyId}`, {
            method: "PATCH",
            body: JSON.stringify({ action: "rotate" }),
        });
    }
    async setKeyScopes(keyId, scopes) {
        return this.request(`/v1/keys/${keyId}/scopes`, {
            method: "POST",
            body: JSON.stringify({ scopes }),
        });
    }
    async setKeyConcurrency(keyId, maxConcurrent) {
        return this.request(`/v1/keys/${keyId}/concurrency`, {
            method: "POST",
            body: JSON.stringify({ max_concurrent: maxConcurrent }),
        });
    }
    async setKeyFileFilter(keyId, allowed, blocked) {
        return this.request(`/v1/keys/${keyId}/file-type-filter`, {
            method: "POST",
            body: JSON.stringify({ allowed_extensions: allowed, blocked_extensions: blocked }),
        });
    }
    async getKeyUsage(keyId) {
        return this.request(`/v1/keys/${keyId}/usage`);
    }
    async getKeyConcurrency(keyId) {
        return this.request(`/v1/keys/${keyId}/concurrency`);
    }
    async getKeyRateLimit(keyId) {
        return this.request(`/v1/keys/${keyId}/rate-limit`);
    }
    async shareKey(keyId, expiresInHours, maxUses) {
        return this.request("/v1/keys/share", {
            method: "POST",
            body: JSON.stringify({ key_id: keyId, expires_in_hours: expiresInHours, max_uses: maxUses }),
        });
    }
    async listKeyShares() {
        return this.request("/v1/keys/shares");
    }
    async scheduleKeyRotation(keyId, intervalDays, enabled) {
        return this.request("/v1/keys/rotation/schedule", {
            method: "POST",
            body: JSON.stringify({ key_id: keyId, interval_days: intervalDays, enabled }),
        });
    }
    async listKeyRotations() {
        return this.request("/v1/keys/rotation");
    }
    async bulkCreateKeys(count, tier, scopes) {
        return this.request("/v1/keys/bulk", {
            method: "POST",
            body: JSON.stringify({ count, tier, scopes }),
        });
    }
    // ---------- Users ----------
    async createUser(body) {
        return this.request("/v1/users", { method: "POST", body: JSON.stringify(body) });
    }
    async listUsers(limit, offset) {
        const params = new URLSearchParams();
        if (limit)
            params.set("limit", String(limit));
        if (offset)
            params.set("offset", String(offset));
        return this.request(`/v1/users?${params}`);
    }
    async getUser(userId) {
        return this.request(`/v1/users/${userId}`);
    }
    async updateUser(userId, body) {
        return this.request(`/v1/users/${userId}`, {
            method: "PUT",
            body: JSON.stringify(body),
        });
    }
    async deleteUser(userId) {
        return this.request(`/v1/users/${userId}`, { method: "DELETE" });
    }
    async setUserTier(userId, tier) {
        return this.request(`/v1/users/${userId}/tier`, {
            method: "POST",
            body: JSON.stringify({ tier }),
        });
    }
    // ---------- Tiers ----------
    async listTiers() {
        return this.request("/v1/tiers");
    }
    async setTierFeature(tier, feature, enabled) {
        return this.request("/v1/tiers/features", {
            method: "POST",
            body: JSON.stringify({ tier, feature, enabled }),
        });
    }
    async getTierFeatures(tier) {
        return this.request(`/v1/tiers/${tier}/features`);
    }
    // ---------- Search ----------
    async searchMusic(query, source, limit) {
        const params = new URLSearchParams({ q: query });
        if (source)
            params.set("source", source);
        if (limit)
            params.set("limit", String(limit));
        return this.request(`/v1/search?${params}`);
    }
    async federatedSearch(query, limit, source) {
        const params = new URLSearchParams({ q: query, limit: String(limit || 10) });
        if (source)
            params.set("source", source);
        return this.request(`/v1/federated-search?${params}`);
    }
    async searchHistory(limit) {
        const params = new URLSearchParams();
        if (limit)
            params.set("limit", String(limit));
        return this.request(`/v1/search/history?${params}`);
    }
    async recordSearchHistory(query, source, resultsCount) {
        return this.request("/v1/search/history", {
            method: "POST",
            body: JSON.stringify({ query, source, results_count: resultsCount }),
        });
    }
    async savedSearches() {
        return this.request("/v1/search/saved");
    }
    async createSavedSearch(name, query, source) {
        return this.request("/v1/search/saved", {
            method: "POST",
            body: JSON.stringify({ name, query, source }),
        });
    }
    async deleteSavedSearch(searchId) {
        return this.request(`/v1/search/saved/${searchId}`, { method: "DELETE" });
    }
    async autocomplete(query, source, limit) {
        return this.request("/v1/search/autocomplete", {
            method: "POST",
            body: JSON.stringify({ query, source, limit }),
        });
    }
    async trending(limit) {
        const params = new URLSearchParams();
        if (limit)
            params.set("limit", String(limit));
        return this.request(`/v1/search/trending?${params}`);
    }
    async getSources() {
        return this.request("/v1/sources");
    }
    // ---------- Info / Lyrics / Metadata ----------
    async getTrackInfo(url, source) {
        const params = new URLSearchParams({ url });
        if (source)
            params.set("source", source);
        return this.request(`/v1/info?${params}`);
    }
    async getLyrics(url) {
        return this.request(`/v1/lyrics?url=${encodeURIComponent(url)}`);
    }
    async getMetadata(url, query) {
        const params = new URLSearchParams();
        if (url)
            params.set("url", url);
        if (query)
            params.set("query", query);
        return this.request(`/v1/metadata?${params}`);
    }
    async rateContent(contentId, rating, review) {
        return this.request("/v1/content/rate", {
            method: "POST",
            body: JSON.stringify({ content_id: contentId, rating, review }),
        });
    }
    async getContentRating(contentId, userId) {
        const params = new URLSearchParams({ content_id: contentId });
        if (userId)
            params.set("user_id", String(userId));
        return this.request(`/v1/content/rate/${contentId}?${params}`);
    }
    // ---------- Download ----------
    async downloadTrack(url, source, body) {
        return this.request("/v1/download", {
            method: "POST",
            body: JSON.stringify({ url, source, ...body }),
        });
    }
    async createAdvancedDownload(body) {
        return this.request("/v1/download/advanced", {
            method: "POST",
            body: JSON.stringify(body),
        });
    }
    async listAdvancedDownloads(userId) {
        const params = new URLSearchParams();
        if (userId)
            params.set("user_id", String(userId));
        return this.request(`/v1/download/advanced?${params}`);
    }
    async getDownloadStatus(jobId) {
        return this.request(`/v1/download/advanced/status/${jobId}`);
    }
    async pauseDownload(jobId) {
        return this.request(`/v1/download/advanced/pause/${jobId}`, { method: "POST" });
    }
    async resumeDownload(jobId) {
        return this.request(`/v1/download/advanced/resume/${jobId}`, { method: "POST" });
    }
    async cancelDownload(jobId) {
        return this.request(`/v1/download/advanced/cancel/${jobId}`, { method: "POST" });
    }
    async setSpeedLimit(keyId, maxKbps) {
        return this.request("/v1/download/speed-limit", {
            method: "POST",
            body: JSON.stringify({ key_id: keyId, max_kbps: maxKbps }),
        });
    }
    async setBandwidthAllocation(keyId, maxBytesPerDay, maxBytesPerMonth) {
        return this.request("/v1/download/bandwidth", {
            method: "POST",
            body: JSON.stringify({ key_id: keyId, max_bytes_per_day: maxBytesPerDay, max_bytes_per_month: maxBytesPerMonth }),
        });
    }
    async setDownloadNotification(jobId, notifyComplete, notifyError, channels) {
        return this.request("/v1/download/notify", {
            method: "POST",
            body: JSON.stringify({ job_id: jobId, notify_on_complete: notifyComplete, notify_on_error: notifyError, channels }),
        });
    }
    async setRetryPolicy(maxRetries, backoffSeconds, retryOnError) {
        return this.request("/v1/download/retry-policy", {
            method: "POST",
            body: JSON.stringify({ max_retries: maxRetries, backoff_seconds: backoffSeconds, retry_on_error: retryOnError }),
        });
    }
    async createDownloadSchedule(url, cronExpression, enabled, format, source) {
        return this.request("/v1/download/schedule", {
            method: "POST",
            body: JSON.stringify({ url, cron_expression: cronExpression, enabled, format, source }),
        });
    }
    async listDownloadSchedules() {
        return this.request("/v1/download/schedule");
    }
    async toggleDownloadSchedule(scheduleId, enabled) {
        return this.request(`/v1/download/schedule/${scheduleId}/toggle`, {
            method: "POST",
            body: JSON.stringify({ enabled }),
        });
    }
    // ---------- Favorites ----------
    async addFavorite(body) {
        return this.request("/v1/favorites", {
            method: "POST",
            body: JSON.stringify(body),
        });
    }
    async listFavorites() {
        return this.request("/v1/favorites");
    }
    async removeFavorite(favId) {
        return this.request(`/v1/favorites/${favId}`, { method: "DELETE" });
    }
    // ---------- Playlists ----------
    async createPlaylist(body) {
        return this.request("/v1/playlists", {
            method: "POST",
            body: JSON.stringify(body),
        });
    }
    async listPlaylists() {
        return this.request("/v1/playlists");
    }
    async getPlaylist(playlistId) {
        return this.request(`/v1/playlists/${playlistId}`);
    }
    async updatePlaylist(playlistId, body) {
        return this.request(`/v1/playlists/${playlistId}`, {
            method: "PUT",
            body: JSON.stringify(body),
        });
    }
    async deletePlaylist(playlistId) {
        return this.request(`/v1/playlists/${playlistId}`, { method: "DELETE" });
    }
    async addPlaylistItem(playlistId, body) {
        return this.request(`/v1/playlists/${playlistId}/items`, {
            method: "POST",
            body: JSON.stringify(body),
        });
    }
    async removePlaylistItem(playlistId, itemId) {
        return this.request(`/v1/playlists/${playlistId}/items/${itemId}`, {
            method: "DELETE",
        });
    }
    // ---------- M3U8/HLS/DASH ----------
    async parseM3u8(url, headers, cookies, proxy) {
        return this.request("/v1/m3u8/parse", {
            method: "POST",
            body: JSON.stringify({ url, headers, cookies, proxy }),
        });
    }
    async downloadM3u8(url, body) {
        return this.request("/v1/m3u8/download", {
            method: "POST",
            body: JSON.stringify({ url, ...body }),
        });
    }
    // ---------- Stats / Analytics ----------
    async getStats() {
        return this.request("/v1/web/stats");
    }
    async getGlobalStats() {
        return this.request("/v1/stats/global");
    }
    async getUsageStats() {
        return this.request("/v1/stats/usage");
    }
    async getSourceStats() {
        const res = await this.request("/v1/stats/sources");
        return res.ok ? res.data || [] : [];
    }
    async getActivityFeed(limit) {
        const params = new URLSearchParams();
        if (limit)
            params.set("limit", String(limit));
        return this.request(`/v1/activity/feed?${params}`);
    }
    async recordActivity(action, details) {
        return this.request("/v1/activity/record", {
            method: "POST",
            body: JSON.stringify({ action, details }),
        });
    }
    // ---------- Notifications ----------
    async listNotifications(unreadOnly) {
        const params = new URLSearchParams();
        if (unreadOnly)
            params.set("unread_only", "true");
        return this.request(`/v1/notifications?${params}`);
    }
    async createNotification(title, message, type = "info") {
        return this.request("/v1/notifications", {
            method: "POST",
            body: JSON.stringify({ title, message, type }),
        });
    }
    async markNotificationRead(notifId) {
        return this.request(`/v1/notifications/${notifId}/read`, { method: "PUT" });
    }
    async getNotificationPrefs() {
        return this.request("/v1/notifications/preferences");
    }
    async setNotificationPrefs(prefs) {
        return this.request("/v1/notifications/preferences", {
            method: "PUT",
            body: JSON.stringify(prefs),
        });
    }
    // ---------- Payments ----------
    async createInvoice(title, description, amount, currency = "XTR") {
        return this.request("/v1/payments/invoice", {
            method: "POST",
            body: JSON.stringify({ title, description, amount, currency }),
        });
    }
    async paymentHistory() {
        return this.request("/v1/payments/history");
    }
    // ---------- Webhooks ----------
    async listWebhooks() {
        return this.request("/v1/webhooks");
    }
    async createWebhook(url, events, secret) {
        return this.request("/v1/webhooks", {
            method: "POST",
            body: JSON.stringify({ url, events, secret }),
        });
    }
    async deleteWebhook(webhookId) {
        return this.request(`/v1/webhooks/${webhookId}`, { method: "DELETE" });
    }
    // ---------- Cache ----------
    async getCacheStats() {
        return this.request("/v1/cache/stats");
    }
    async clearCache() {
        return this.request("/v1/cache/clear", { method: "POST" });
    }
    async invalidateCacheTag(tag) {
        return this.request(`/v1/cache/invalidate/${tag}`, { method: "POST" });
    }
    async warmCache(queries, source, limitPerQuery) {
        return this.request("/v1/cache/warm", {
            method: "POST",
            body: JSON.stringify({ queries, source, limit_per_query: limitPerQuery }),
        });
    }
    // ---------- Scheduler ----------
    async listSchedulerTasks() {
        return this.request("/v1/scheduler/tasks");
    }
    async enableSchedulerTask(name) {
        return this.request(`/v1/scheduler/tasks/${name}/enable`, { method: "POST" });
    }
    async disableSchedulerTask(name) {
        return this.request(`/v1/scheduler/tasks/${name}/disable`, { method: "POST" });
    }
    // ---------- Plugins ----------
    async listPlugins() {
        return this.request("/v1/plugins");
    }
    async enablePlugin(pluginId) {
        return this.request(`/v1/plugins/${pluginId}/enable`, { method: "POST" });
    }
    async disablePlugin(pluginId) {
        return this.request(`/v1/plugins/${pluginId}/disable`, { method: "POST" });
    }
    // ---------- System ----------
    async getSystemInfo() {
        return this.request("/v1/system/info");
    }
    async getSystemDisk() {
        return this.request("/v1/system/disk");
    }
    async getSystemMemory() {
        return this.request("/v1/system/memory");
    }
    async getConfig() {
        return this.request("/v1/config");
    }
    async getVersion() {
        return this.request("/v1/version");
    }
    async getMaintenance() {
        return this.request("/v1/maintenance");
    }
    // ---------- Geo / IP ----------
    async geoCheck(countryCode) {
        return this.request(`/v1/geo/check/${countryCode}`);
    }
    async listGeoBlocks() {
        return this.request("/v1/geo/blocked");
    }
    async getIpReputation(ip) {
        return this.request(`/v1/ip/reputation/${ip}`);
    }
    // ---------- Sessions ----------
    async listSessions() {
        return this.request("/v1/sessions");
    }
    async revokeSession(sessionId) {
        return this.request(`/v1/sessions/${sessionId}`, { method: "DELETE" });
    }
    // ---------- Teams ----------
    async listTeams() {
        return this.request("/v1/teams");
    }
    async createTeam(name) {
        return this.request("/v1/teams", {
            method: "POST",
            body: JSON.stringify({ name }),
        });
    }
    // ---------- Export ----------
    async exportHistory(format = "json") {
        return this.request("/v1/export/history", {
            method: "POST",
            body: JSON.stringify({ format }),
        });
    }
    async listExports() {
        return this.request("/v1/export/history");
    }
    // ---------- Files ----------
    async listFiles() {
        return this.request("/v1/files");
    }
    async deleteFile(folder, filename) {
        return this.request(`/v1/files/${folder}/${filename}`, { method: "DELETE" });
    }
    // ---------- Reports ----------
    async createUsageReport(period = "monthly", format = "csv") {
        return this.request("/v1/reports/usage", {
            method: "POST",
            body: JSON.stringify({ period, format }),
        });
    }
    async listUsageReports() {
        return this.request("/v1/reports/usage");
    }
    // ---------- Suspicious Activity ----------
    async listSuspiciousActivity(limit) {
        const params = new URLSearchParams();
        if (limit)
            params.set("limit", String(limit));
        return this.request(`/v1/suspicious-activity?${params}`);
    }
    // ---------- Moderation ----------
    async listModeration(status) {
        const params = new URLSearchParams();
        if (status)
            params.set("status", status);
        return this.request(`/v1/moderation?${params}`);
    }
    // ---------- WebSocket ----------
    wsConnect(userId) {
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
                }
                catch { }
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
        }
        catch { }
    }
    wsDisconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
    wsSubscribe(channel) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ action: "subscribe", channel }));
        }
    }
    wsUnsubscribe(channel) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ action: "unsubscribe", channel }));
        }
    }
    wsPing(timestamp) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ action: "ping", timestamp }));
        }
    }
    on(event, callback) {
        if (!this.wsListeners.has(event)) {
            this.wsListeners.set(event, []);
        }
        this.wsListeners.get(event).push(callback);
    }
    off(event, callback) {
        const listeners = this.wsListeners.get(event);
        if (listeners) {
            const idx = listeners.indexOf(callback);
            if (idx >= 0)
                listeners.splice(idx, 1);
        }
    }
    emit(event, data) {
        const listeners = this.wsListeners.get(event);
        if (listeners) {
            listeners.forEach((cb) => cb(data));
        }
    }
    getWsConnected() {
        return this.ws?.readyState === WebSocket.OPEN;
    }
}
const api = new ApiClient();
/**
 * State Management - TypeScript
 * Centralized app state with reactivity
 */
const defaultState = {
    user: null,
    token: null,
    keys: [],
    stats: {},
    sources: [],
    searchResults: [],
    downloads: [],
    favorites: [],
    playlists: [],
    notifications: [],
    activityFeed: [],
    theme: "system",
    language: "en",
    isOnline: true,
    wsConnected: false,
    currentView: "auth",
    modals: {},
};
class Store {
    constructor() {
        this.state = { ...defaultState };
        this.listeners = new Set();
    }
    subscribe(listener) {
        this.listeners.add(listener);
        return () => {
            this.listeners.delete(listener);
        };
    }
    getState() {
        return this.state;
    }
    setState(partial) {
        this.state = { ...this.state, ...partial };
        this.listeners.forEach((l) => l());
    }
    // Convenience
    get user() { return this.state.user; }
    get token() { return this.state.token; }
    get keys() { return this.state.keys; }
    get stats() { return this.state.stats; }
    get sources() { return this.state.sources; }
    get downloads() { return this.state.downloads; }
    get favorites() { return this.state.favorites; }
    get playlists() { return this.state.playlists; }
    get notifications() { return this.state.notifications; }
    get activityFeed() { return this.state.activityFeed; }
    get currentView() { return this.state.currentView; }
    get wsConnected() { return this.state.wsConnected; }
    get isOnline() { return this.state.isOnline; }
    setUser(user, token = null) {
        this.setState({ user, token });
        if (token)
            localStorage.setItem("videl_token", token);
        else
            localStorage.removeItem("videl_token");
    }
    setKeys(keys) {
        this.setState({ keys });
    }
    setStats(stats) {
        this.setState({ stats });
    }
    setSources(sources) {
        this.setState({ sources });
    }
    setDownloads(downloads) {
        this.setState({ downloads });
    }
    addDownload(download) {
        this.setState({ downloads: [download, ...this.state.downloads] });
    }
    updateDownload(jobId, updates) {
        this.setState({
            downloads: this.state.downloads.map((d) => d.job_id === jobId ? { ...d, ...updates } : d),
        });
    }
    removeDownload(jobId) {
        this.setState({
            downloads: this.state.downloads.filter((d) => d.job_id !== jobId),
        });
    }
    setFavorites(favorites) {
        this.setState({ favorites });
    }
    setPlaylists(playlists) {
        this.setState({ playlists });
    }
    setNotifications(notifications) {
        this.setState({ notifications });
    }
    setActivityFeed(feed) {
        this.setState({ activityFeed: feed });
    }
    setCurrentView(view) {
        this.setState({ currentView: view });
    }
    setWsConnected(connected) {
        this.setState({ wsConnected: connected });
    }
    setOnline(online) {
        this.setState({ isOnline: online });
    }
    openModal(name) {
        this.setState({ modals: { ...this.state.modals, [name]: true } });
    }
    closeModal(name) {
        const modals = { ...this.state.modals };
        delete modals[name];
        this.setState({ modals });
    }
    loadPersisted() {
        const token = localStorage.getItem("videl_token");
        if (token) {
            this.state.token = token;
        }
        const theme = localStorage.getItem("videl_theme");
        if (theme)
            this.state.theme = theme;
        const lang = localStorage.getItem("videl_language");
        if (lang)
            this.state.language = lang;
    }
}
const store = new Store();
/**
 * UI Components - TypeScript
 * Comprehensive component library for Videl-Api WebApp
 */
// ---- DOM helpers ----
function el(tag, props = {}, children = []) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
        if (k === "className")
            e.className = v;
        else if (k === "innerHTML")
            e.innerHTML = v;
        else if (k === "textContent")
            e.textContent = v;
        else if (k.startsWith("on") && typeof v === "function") {
            e.addEventListener(k.slice(2).toLowerCase(), v);
        }
        else if (k === "style" && typeof v === "object") {
            Object.assign(e.style, v);
        }
        else {
            e.setAttribute(k, String(v));
        }
    }
    for (const child of children) {
        if (child instanceof HTMLElement)
            e.appendChild(child);
        else if (typeof child === "string")
            e.appendChild(document.createTextNode(child));
        else if (child)
            e.appendChild(document.createTextNode(String(child)));
    }
    return e;
}
function clear(container) {
    container.innerHTML = "";
}
// ---- Format helpers ----
function formatBytes(bytes) {
    if (bytes === 0)
        return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}
function formatNumber(n) {
    return n.toLocaleString();
}
function formatDuration(seconds) {
    if (!seconds)
        return "--";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return h > 0 ? `${h}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}` : `${m}:${s.toString().padStart(2, "0")}`;
}
function formatDate(iso) {
    if (!iso)
        return "--";
    try {
        return new Date(iso).toLocaleString();
    }
    catch {
        return iso;
    }
}
function tierColor(tier) {
    const colors = {
        free: "#00b894",
        pro: "#6c5ce7",
        owner: "#ffd700",
    };
    return colors[tier] || "#666";
}
function tierBadge(tier) {
    return el("span", {
        className: "tier-badge",
        style: {
            background: tierColor(tier) + "20",
            color: tierColor(tier),
            padding: "4px 10px",
            borderRadius: "12px",
            fontSize: "0.7rem",
            fontWeight: "700",
            textTransform: "uppercase",
            border: `1px solid ${tierColor(tier)}40`,
        },
        textContent: tier.toUpperCase(),
    });
}
// ---- Status helpers ----
function statusBadge(status) {
    const colors = {
        queued: "#6c5ce7",
        downloading: "#0088cc",
        paused: "#ffd700",
        completed: "#00b894",
        failed: "#d63031",
        cancelled: "#b2bec3",
    };
    return el("span", {
        className: "status-badge",
        style: {
            background: (colors[status] || "#666") + "20",
            color: colors[status] || "#666",
            padding: "4px 10px",
            borderRadius: "12px",
            fontSize: "0.7rem",
            fontWeight: "700",
            textTransform: "uppercase",
            border: `1px solid ${(colors[status] || "#666")}40`,
        },
        textContent: status.toUpperCase(),
    });
}
// ---- Progress bar ----
function progressBar(progress, fillClass) {
    return el("div", {
        className: "progress-container",
        style: {
            width: "100%",
            height: "6px",
            background: "#e9ecef",
            borderRadius: "3px",
            overflow: "hidden",
            marginTop: "8px",
        },
        children: [
            el("div", {
                className: fillClass || "",
                style: {
                    width: `${Math.min(100, Math.max(0, progress))}%`,
                    height: "100%",
                    background: "linear-gradient(90deg, #0088cc, #00b894)",
                    transition: "width 0.3s ease",
                },
            }),
        ],
    });
}
// ---- Layout ----
function renderPageHeader(title, subtitle) {
    return el("header", {
        className: "page-header",
        style: {
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "24px",
            paddingBottom: "16px",
            borderBottom: "1px solid #eaeaea",
        },
        children: [
            el("div", {
                children: [
                    el("h1", {
                        textContent: title,
                        style: { margin: 0, fontSize: "1.25rem", color: "#1a1a2e" },
                    }),
                    subtitle && el("p", {
                        textContent: subtitle,
                        style: { margin: "4px 0 0", color: "#666", fontSize: "0.9rem" },
                    }),
                ],
            }),
        ],
    });
}
function renderCard(children, style) {
    return el("div", {
        className: "card",
        style: {
            background: "#fff",
            borderRadius: "16px",
            boxShadow: "0 4px 20px rgba(0,0,0,0.06)",
            border: "1px solid #f0f0f0",
            padding: "20px",
            ...style,
        },
        children,
    });
}
// ---- Buttons ----
function btnPrimary(text, onClick, disabled = false) {
    return el("button", {
        className: "btn-primary",
        style: {
            width: "100%",
            padding: "14px",
            fontSize: "1rem",
            fontWeight: "700",
            background: disabled ? "#b2bec3" : "linear-gradient(135deg, #0088cc, #005588)",
            color: "#fff",
            border: "none",
            borderRadius: "10px",
            cursor: disabled ? "not-allowed" : "pointer",
            opacity: disabled ? 0.6 : 1,
        },
        disabled,
        textContent: text,
        onClick,
    });
}
function btnSecondary(text, onClick, danger = false) {
    return el("button", {
        style: {
            padding: "10px 18px",
            fontSize: "0.9rem",
            fontWeight: "600",
            background: danger ? "#fee2e2" : "#f3f4f6",
            color: danger ? "#d63031" : "#1a1a2e",
            border: "none",
            borderRadius: "8px",
            cursor: "pointer",
        },
        textContent: text,
        onClick: () => {
            haptic("light");
            onClick();
        },
    });
}
// ---- Stat Card ----
function renderStatCard(label, value, color, icon) {
    return el("div", {
        className: "stat-card",
        style: {
            background: "#fff",
            padding: "20px",
            borderRadius: "16px",
            boxShadow: "0 4px 20px rgba(0,0,0,0.06)",
            border: "1px solid #f0f0f0",
            display: "flex",
            flexDirection: "column",
            gap: "8px",
        },
        children: [
            el("div", {
                style: { display: "flex", alignItems: "center", gap: "10px" },
                children: [
                    icon ? el("span", { textContent: icon, style: { fontSize: "1.2rem" } }) : null,
                    el("div", {
                        textContent: label,
                        style: { fontSize: "0.85rem", color: "#999", marginBottom: "4px" },
                    }),
                ],
            }),
            el("div", {
                textContent: value,
                style: { fontSize: "1.75rem", fontWeight: "800", color },
            }),
        ],
    });
}
// ---- Empty State ----
function renderEmptyState(icon, title, subtitle, action) {
    return el("div", {
        className: "empty-state",
        style: {
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            padding: "48px 20px",
            textAlign: "center",
        },
        children: [
            el("div", { textContent: icon, style: { fontSize: "3rem", marginBottom: "16px" } }),
            el("h3", { textContent: title, style: { marginBottom: "8px", color: "#1a1a2e" } }),
            subtitle && el("p", {
                textContent: subtitle,
                style: { color: "#666", marginBottom: "20px", fontSize: "0.95rem" },
            }),
            action && btnPrimary(action.text, action.onClick),
        ],
    });
}
// ---- Loading ----
function renderLoading(container) {
    clear(container);
    container.appendChild(el("div", {
        className: "loading",
        style: {
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            padding: "60px 20px",
            color: "#666",
        },
        children: [
            el("div", {
                style: {
                    width: "40px",
                    height: "40px",
                    border: "4px solid #f3f3f3",
                    borderTop: "4px solid #0088cc",
                    borderRadius: "50%",
                    animation: "spin 1s linear infinite",
                    marginBottom: "16px",
                },
            }),
            el("div", { textContent: "Loading..." }),
        ],
    }));
}
// ---- Auth Screen ----
function renderAuthScreen(container, onAuth) {
    clear(container);
    const user = window.Telegram?.WebApp?.initDataUnsafe?.user;
    if (user) {
        onAuth(user);
        return;
    }
    container.appendChild(el("div", {
        className: "auth-card",
        style: {
            maxWidth: "420px",
            margin: "0 auto",
            padding: "40px",
            background: "#fff",
            borderRadius: "20px",
            boxShadow: "0 20px 60px rgba(0,0,0,0.12)",
            textAlign: "center",
        },
        children: [
            el("div", {
                style: {
                    width: "64px",
                    height: "64px",
                    background: "linear-gradient(135deg, #0088cc, #005588)",
                    borderRadius: "16px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    margin: "0 auto 24px",
                    color: "#fff",
                    fontSize: "28px",
                },
                textContent: "V",
            }),
            el("h2", { textContent: "Videl-Api", style: { marginBottom: "8px" } }),
            el("p", {
                textContent: "Sign in with Telegram to create and manage your API keys",
                style: { color: "#666", marginBottom: "32px", fontSize: "1.1rem" },
            }),
            btnPrimary("🔐 Sign in with Telegram", () => {
                if (!isTelegramWebApp()) {
                    showAlert("Please open this in Telegram WebApp");
                    return;
                }
                tg?.sendData("auth");
            }),
            el("p", {
                textContent: "Or open this link in Telegram: /getapi",
                style: { color: "#999", fontSize: "0.9rem", marginTop: "20px" },
            }),
        ],
    }));
}
// ---- Dashboard ----
async function renderDashboard(container, user) {
    clear(container);
    const s = store;
    // Header
    const wsStatus = el("div", {
        className: "ws-status disconnected",
        id: "ws-status",
        children: [
            el("div", { className: "ws-dot" }),
            el("span", { textContent: "Realtime: Disconnected" }),
        ],
    });
    const header = el("header", {
        className: "dashboard-header",
        style: {
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "16px",
            marginBottom: "32px",
        },
        children: [
            el("div", {
                style: { display: "flex", alignItems: "center", gap: "16px", flex: 1 },
                children: [
                    el("img", {
                        src: user.photo_url || "https://via.placeholder.com/48",
                        alt: "avatar",
                        style: { width: "48px", height: "48px", borderRadius: "50%" },
                    }),
                    el("div", {
                        children: [
                            el("h1", {
                                textContent: `Welcome, ${user.first_name}`,
                                style: { margin: 0, fontSize: "1.5rem", color: "#1a1a2e" },
                            }),
                            el("p", {
                                textContent: user.username ? `@${user.username}` : "Telegram User",
                                style: { margin: 0, color: "#666", fontSize: "0.9rem" },
                            }),
                        ],
                    }),
                ],
            }),
            wsStatus,
        ],
    });
    // Stats grid
    const statsGrid = el("div", {
        className: "stats-grid",
        style: {
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
            gap: "16px",
            marginBottom: "32px",
        },
    });
    const statCards = {
        requests_today: { label: "Today Requests", value: "0", color: "#0088cc", icon: "📊" },
        requests_month: { label: "Month Requests", value: "0", color: "#00b894", icon: "📈" },
        bytes_today: { label: "Today Bandwidth", value: "0 B", color: "#6c5ce7", icon: "⬇️" },
        bytes_month: { label: "Month Bandwidth", value: "0 B", color: "#ffd700", icon: "⬇️" },
    };
    for (const [key, stat] of Object.entries(statCards)) {
        statsGrid.appendChild(renderStatCard(stat.label, stat.value, stat.color, stat.icon));
    }
    // Key section
    const keySection = el("div", {
        className: "key-section",
        style: { marginBottom: "32px" },
        children: [
            el("div", {
                style: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" },
                children: [
                    el("h2", { textContent: "Your API Keys", style: { margin: 0, color: "#1a1a2e" } }),
                    tierBadge(s.user?.tier || "free"),
                ],
            }),
            el("div", {
                className: "keys-list",
                id: "keys-list",
                style: {
                    display: "flex",
                    flexDirection: "column",
                    gap: "12px",
                },
            }),
            btnPrimary("+ Create New API Key", () => {
                s.openModal("create-key");
            }),
        ],
    });
    container.appendChild(header);
    container.appendChild(statsGrid);
    container.appendChild(keySection);
    // Modals
    container.appendChild(renderCreateKeyModal());
    container.appendChild(renderKeyResultModal());
    // Load data
    await loadKeys();
    await loadStats();
    async function loadKeys() {
        const list = document.getElementById("keys-list");
        if (!list)
            return;
        clear(list);
        try {
            const res = await api.listKeys();
            if (!res.ok || !res.data) {
                list.appendChild(el("div", {
                    style: { textAlign: "center", color: "#666", padding: "20px" },
                    textContent: "Unable to load keys",
                }));
                return;
            }
            const keys = res.data.keys || [];
            s.setKeys(keys);
            if (keys.length === 0) {
                list.appendChild(renderEmptyState("🔑", "No API keys yet", "Create your first key to access the API", {
                    text: "Create Key",
                    onClick: () => s.openModal("create-key"),
                }));
                return;
            }
            for (const k of keys) {
                list.appendChild(renderKeyCard(k));
            }
        }
        catch (err) {
            list.appendChild(renderEmptyState("⚠️", "Failed to load keys", err.message || "Unknown error"));
        }
    }
    async function loadStats() {
        try {
            const res = await api.getStats();
            if (res.ok && res.data) {
                const data = res.data;
                for (const [key, value] of Object.entries(data)) {
                    const el = document.getElementById(`stat-${key}`);
                    if (el) {
                        if (key.includes("bytes")) {
                            el.textContent = formatBytes(Number(value));
                        }
                        else {
                            el.textContent = formatNumber(Number(value));
                        }
                    }
                }
            }
        }
        catch (err) {
            console.error("Stats error:", err);
        }
    }
}
// ---- Key Card ----
function renderKeyCard(k) {
    const s = store;
    return el("div", {
        className: "key-card",
        style: {
            background: "#fff",
            padding: "20px",
            borderRadius: "16px",
            boxShadow: "0 4px 20px rgba(0,0,0,0.06)",
            border: "1px solid #f0f0f0",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            transition: "all 0.2s ease",
        },
        children: [
            el("div", {
                style: { flex: 1, minWidth: 0 },
                children: [
                    el("div", {
                        style: { display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px" },
                        children: [
                            tierBadge(k.tier),
                            el("span", {
                                textContent: k.active ? "● Active" : "○ Inactive",
                                style: {
                                    fontSize: "0.85rem",
                                    color: k.active ? "#00b894" : "#d63031",
                                    fontWeight: "600",
                                },
                            }),
                        ],
                    }),
                    el("div", {
                        textContent: k.label || `Key ${k.key_prefix}`,
                        style: { fontSize: "1rem", fontWeight: "700", color: "#1a1a2e" },
                    }),
                    el("div", {
                        textContent: k.key_prefix,
                        style: { fontSize: "0.85rem", color: "#666", fontFamily: "monospace", marginTop: "4px" },
                    }),
                    el("div", {
                        textContent: `Scopes: ${k.scopes.join(", ")}`,
                        style: { fontSize: "0.8rem", color: "#999", marginTop: "4px" },
                    }),
                    k.rate_limit !== undefined && el("div", {
                        textContent: `Rate: ${k.rate_limit} req/min`,
                        style: { fontSize: "0.8rem", color: "#999", marginTop: "2px" },
                    }),
                ],
            }),
            el("div", {
                style: { display: "flex", gap: "8px", alignItems: "center" },
                children: [
                    btnSecondary("Revoke", async () => {
                        const ok = await showConfirmAsync("Revoke this API key?");
                        if (ok) {
                            await api.revokeKey(k.key_id);
                            haptic("success");
                            const list = document.getElementById("keys-list");
                            if (list) {
                                const card = list.querySelector(`[data-key-id="${k.key_id}"]`);
                                card?.remove();
                            }
                        }
                    }, true),
                    btnSecondary("Rotate", async () => {
                        const res = await api.rotateKey(k.key_id);
                        if (res.ok) {
                            showAlert(`New key: ${res.data?.new_key}`);
                            haptic("success");
                        }
                        else {
                            showAlert(res.error || "Failed to rotate key");
                        }
                    }),
                ],
            }),
        ],
    });
}
function showConfirmAsync(message) {
    return new Promise((resolve) => {
        showConfirm(message, (confirmed) => resolve(confirmed));
    });
}
// ---- Create Key Modal ----
function renderCreateKeyModal() {
    const s = store;
    const modal = el("div", {
        id: "create-key-modal",
        className: "modal",
        style: {
            display: "none",
            position: "fixed",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            background: "rgba(0,0,0,0.5)",
            zIndex: "1000",
            alignItems: "center",
            justifyContent: "center",
            backdropFilter: "blur(4px)",
        },
        children: [
            el("div", {
                className: "modal-content",
                style: {
                    background: "#fff",
                    borderRadius: "20px",
                    padding: "32px",
                    maxWidth: "450px",
                    width: "90%",
                    maxHeight: "90vh",
                    overflowY: "auto",
                },
                children: [
                    el("h2", { textContent: "Create API Key", style: { marginBottom: "20px", color: "#1a1a2e" } }),
                    el("div", {
                        style: { marginBottom: "20px" },
                        children: [
                            el("label", {
                                textContent: "Tier",
                                style: { display: "block", marginBottom: "8px", fontWeight: "600", color: "#1a1a2e" },
                            }),
                            el("select", {
                                id: "key-tier",
                                style: {
                                    width: "100%",
                                    padding: "12px",
                                    border: "1px solid #ddd",
                                    borderRadius: "10px",
                                    fontSize: "1rem",
                                    marginBottom: "16px",
                                },
                                children: [
                                    el("option", { value: "free", textContent: "Free — 100 req/day" }),
                                    el("option", { value: "pro", textContent: "Pro — 1,000 req/day + downloads" }),
                                    el("option", { value: "owner", textContent: "Owner — Unlimited (admin)" }),
                                ],
                            }),
                            el("label", {
                                textContent: "Label (optional)",
                                style: { display: "block", marginBottom: "8px", fontWeight: "600", color: "#1a1a2e" },
                            }),
                            el("input", {
                                id: "key-label",
                                type: "text",
                                placeholder: "e.g. My Music Bot",
                                style: {
                                    width: "100%",
                                    padding: "12px",
                                    border: "1px solid #ddd",
                                    borderRadius: "10px",
                                    fontSize: "1rem",
                                    marginBottom: "16px",
                                },
                            }),
                            el("label", {
                                textContent: "Expires In (days, optional)",
                                style: { display: "block", marginBottom: "8px", fontWeight: "600", color: "#1a1a2e" },
                            }),
                            el("input", {
                                id: "key-expires",
                                type: "number",
                                min: "1",
                                style: {
                                    width: "100%",
                                    padding: "12px",
                                    border: "1px solid #ddd",
                                    borderRadius: "10px",
                                    fontSize: "1rem",
                                    marginBottom: "24px",
                                },
                            }),
                        ],
                    }),
                    el("div", {
                        style: { display: "flex", gap: "10px" },
                        children: [
                            el("button", {
                                id: "create-key-cancel",
                                style: {
                                    flex: 1,
                                    padding: "14px",
                                    fontSize: "1rem",
                                    fontWeight: "700",
                                    background: "#f5f5f5",
                                    border: "1px solid #ddd",
                                    borderRadius: "10px",
                                    color: "#666",
                                    cursor: "pointer",
                                },
                                textContent: "Cancel",
                                onClick: () => {
                                    modal.style.display = "none";
                                    s.closeModal("create-key");
                                },
                            }),
                            btnPrimary("Create Key", async () => {
                                const tierSelect = document.getElementById("key-tier");
                                const labelInput = document.getElementById("key-label");
                                const expiresInput = document.getElementById("key-expires");
                                const tier = tierSelect.value;
                                const label = labelInput.value || undefined;
                                const expires = expiresInput.value ? parseInt(expiresInput.value) : undefined;
                                const btn = document.getElementById("create-key-cancel");
                                btn.disabled = true;
                                btn.textContent = "Creating...";
                                try {
                                    const res = await api.createKey({ tier, label, expires_in_days: expires });
                                    if (res.ok && res.data) {
                                        const data = res.data;
                                        const input = document.getElementById("key-value-display");
                                        input.value = data.key || "";
                                        modal.style.display = "none";
                                        s.closeModal("create-key");
                                        s.openModal("key-result");
                                        haptic("success");
                                    }
                                    else {
                                        showAlert(res.error || "Failed to create key");
                                    }
                                }
                                catch (err) {
                                    showAlert(err.message || "Error creating key");
                                }
                                finally {
                                    btn.disabled = false;
                                    btn.textContent = "Cancel";
                                }
                            }),
                        ],
                    }),
                ],
            }),
        ],
    });
    // Close on outside click
    modal.addEventListener("click", (e) => {
        if (e.target === modal) {
            modal.style.display = "none";
            s.closeModal("create-key");
        }
    });
    return modal;
}
// ---- Key Result Modal ----
function renderKeyResultModal() {
    const s = store;
    const modal = el("div", {
        id: "key-result-modal",
        className: "modal",
        style: {
            display: "none",
            position: "fixed",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            background: "rgba(0,0,0,0.5)",
            zIndex: "1000",
            alignItems: "center",
            justifyContent: "center",
            backdropFilter: "blur(4px)",
        },
        children: [
            el("div", {
                className: "modal-content",
                style: {
                    background: "#fff",
                    borderRadius: "20px",
                    padding: "32px",
                    maxWidth: "450px",
                    width: "90%",
                },
                children: [
                    el("h2", { textContent: "🔑 Your API Key", style: { marginBottom: "16px", color: "#1a1a2e" } }),
                    el("p", {
                        textContent: "Save this key securely. It won't be shown again.",
                        style: { color: "#666", marginBottom: "20px", fontSize: "0.9rem" },
                    }),
                    el("div", {
                        style: {
                            background: "#f8f9fa",
                            border: "1px solid #eaeaea",
                            borderRadius: "12px",
                            padding: "16px",
                            marginBottom: "20px",
                            display: "flex",
                            gap: "10px",
                            alignItems: "center",
                        },
                        children: [
                            el("input", {
                                id: "key-value-display",
                                type: "text",
                                readonly: true,
                                style: {
                                    flex: 1,
                                    padding: "10px",
                                    border: "none",
                                    background: "transparent",
                                    fontFamily: "monospace",
                                    fontSize: "0.9rem",
                                    color: "#1a1a2e",
                                },
                            }),
                            el("button", {
                                textContent: "Copy",
                                style: {
                                    padding: "8px 16px",
                                    background: "#0088cc",
                                    color: "#fff",
                                    border: "none",
                                    borderRadius: "8px",
                                    fontWeight: "600",
                                    cursor: "pointer",
                                },
                                onClick: () => {
                                    const input = document.getElementById("key-value-display");
                                    input.select();
                                    document.execCommand("copy");
                                    haptic("success");
                                    showAlert("Copied to clipboard!");
                                },
                            }),
                        ],
                    }),
                    btnPrimary("Done", () => {
                        modal.style.display = "none";
                        s.closeModal("key-result");
                        const list = document.getElementById("keys-list");
                        if (list) {
                            // Trigger reload by finding the dashboard
                            const event = new CustomEvent("reload-keys");
                            window.dispatchEvent(event);
                        }
                    }),
                ],
            }),
        ],
    });
    modal.addEventListener("click", (e) => {
        if (e.target === modal) {
            modal.style.display = "none";
            s.closeModal("key-result");
        }
    });
    return modal;
}
// ---- Sources Screen ----
async function renderSources(container) {
    clear(container);
    container.appendChild(el("div", {
        className: "loading",
        style: {
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            padding: "40px 20px",
        },
        children: [
            el("div", {
                style: {
                    width: "32px",
                    height: "32px",
                    border: "3px solid #f3f3f3",
                    borderTop: "3px solid #0088cc",
                    borderRadius: "50%",
                    animation: "spin 1s linear infinite",
                    marginBottom: "12px",
                },
            }),
            el("div", { textContent: "Loading sources..." }),
        ],
    }));
    try {
        const res = await api.getSources();
        clear(container);
        if (!res.ok || !res.data) {
            container.appendChild(renderEmptyState("⚠️", "Failed to load sources", res.error || "Unknown error"));
            return;
        }
        const sources = res.data.sources || [];
        container.appendChild(el("h2", {
            textContent: "Supported Sources",
            style: { marginBottom: "20px", color: "#1a1a2e" },
        }));
        const grid = el("div", {
            style: {
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
                gap: "16px",
            },
        });
        for (const s of sources) {
            grid.appendChild(el("div", {
                className: "source-card",
                style: {
                    background: "#fff",
                    padding: "16px",
                    borderRadius: "12px",
                    boxShadow: "0 2px 10px rgba(0,0,0,0.05)",
                    border: "1px solid #f0f0f0",
                    transition: "all 0.2s ease",
                },
                children: [
                    el("div", {
                        style: {
                            display: "flex",
                            alignItems: "center",
                            gap: "8px",
                            marginBottom: "8px",
                        },
                        children: [
                            el("span", {
                                textContent: s.supports_search ? "🔍 Search" : "📋 URL only",
                                style: { fontSize: "0.75rem", color: "#666" },
                            }),
                        ],
                    }),
                    el("div", {
                        textContent: s.name,
                        style: { fontSize: "1.1rem", fontWeight: "700", color: "#1a1a2e", marginBottom: "6px" },
                    }),
                    el("div", {
                        textContent: s.description,
                        style: { fontSize: "0.85rem", color: "#666", lineHeight: "1.4" },
                    }),
                ],
            }));
        }
        container.appendChild(grid);
    }
    catch (err) {
        container.appendChild(renderEmptyState("⚠️", "Failed to load sources", err.message || "Unknown error"));
    }
}
// ---- Search Screen ----
async function renderSearch(container) {
    clear(container);
    const searchInput = el("input", {
        type: "text",
        placeholder: "Search music & media...",
        style: {
            width: "100%",
            padding: "14px",
            border: "1px solid #ddd",
            borderRadius: "10px",
            fontSize: "1rem",
            marginBottom: "20px",
        },
    });
    const sourceSelect = el("select", {
        id: "search-source",
        style: {
            width: "100%",
            padding: "12px",
            border: "1px solid #ddd",
            borderRadius: "10px",
            fontSize: "0.95rem",
            marginBottom: "20px",
        },
        children: [
            el("option", { value: "youtube", textContent: "YouTube" }),
            el("option", { value: "soundcloud", textContent: "SoundCloud" }),
            el("option", { value: "bandcamp", textContent: "Bandcamp" }),
            el("option", { value: "spotify", textContent: "Spotify" }),
            el("option", { value: "apple_music", textContent: "Apple Music" }),
            el("option", { value: "deezer", textContent: "Deezer" }),
        ],
    });
    const resultsContainer = el("div", {
        id: "search-results",
        style: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "16px" },
    });
    container.appendChild(el("div", {
        style: { maxWidth: "600px", margin: "0 auto" },
        children: [
            el("h2", { textContent: "🔍 Search", style: { marginBottom: "20px", color: "#1a1a2e" } }),
            searchInput,
            sourceSelect,
            btnPrimary("Search", async () => {
                const q = searchInput.value.trim();
                if (!q)
                    return;
                const source = sourceSelect.value;
                haptic("light");
                renderLoading(resultsContainer);
                try {
                    const res = await api.searchMusic(q, source, 10);
                    clear(resultsContainer);
                    if (res.ok && res.data) {
                        const results = res.data.results || [];
                        if (results.length === 0) {
                            resultsContainer.appendChild(renderEmptyState("🔍", "No results found", "Try a different query"));
                        }
                        else {
                            for (const r of results) {
                                resultsContainer.appendChild(renderSearchResult(r));
                            }
                        }
                    }
                    else {
                        resultsContainer.appendChild(renderEmptyState("⚠️", "Search failed", res.error || "Unknown error"));
                    }
                }
                catch (err) {
                    resultsContainer.appendChild(renderEmptyState("⚠️", "Search failed", err.message || "Unknown error"));
                }
            }),
            resultsContainer,
        ],
    }));
    // Enter key to search
    searchInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
            searchInput.parentElement?.querySelector("button")?.click();
        }
    });
}
function renderSearchResult(r) {
    return el("div", {
        className: "source-card",
        style: {
            background: "#fff",
            padding: "16px",
            borderRadius: "12px",
            boxShadow: "0 2px 10px rgba(0,0,0,0.05)",
            border: "1px solid #f0f0f0",
        },
        children: [
            el("div", {
                textContent: r.title || "Unknown",
                style: { fontSize: "1rem", fontWeight: "700", color: "#1a1a2e", marginBottom: "6px" },
            }),
            r.uploader && el("div", {
                textContent: r.uploader,
                style: { fontSize: "0.85rem", color: "#666", marginBottom: "6px" },
            }),
            r.duration && el("div", {
                textContent: formatDuration(r.duration),
                style: { fontSize: "0.85rem", color: "#999", marginBottom: "12px" },
            }),
            el("button", {
                textContent: "Download",
                style: {
                    width: "100%",
                    padding: "10px",
                    background: "#0088cc",
                    color: "#fff",
                    border: "none",
                    borderRadius: "8px",
                    fontWeight: "600",
                    cursor: "pointer",
                },
                onClick: () => {
                    haptic("light");
                    window.videlApi?.nav?.("download") || alert("Download feature coming soon");
                },
            }),
        ],
    });
}
// ---- Download Manager Screen ----
async function renderDownloads(container) {
    clear(container);
    container.appendChild(el("h2", {
        textContent: "Download Manager",
        style: { marginBottom: "20px", color: "#1a1a2e" },
    }));
    const urlInput = el("input", {
        type: "text",
        placeholder: "Enter URL to download...",
        style: {
            width: "100%",
            padding: "14px",
            border: "1px solid #ddd",
            borderRadius: "10px",
            fontSize: "1rem",
            marginBottom: "12px",
        },
    });
    const prioritySelect = el("select", {
        style: {
            width: "100%",
            padding: "12px",
            border: "1px solid #ddd",
            borderRadius: "10px",
            fontSize: "0.95rem",
            marginBottom: "20px",
        },
        children: [
            el("option", { value: "normal", textContent: "Normal Priority" }),
            el("option", { value: "high", textContent: "High Priority" }),
            el("option", { value: "low", textContent: "Low Priority" }),
        ],
    });
    const downloadsList = el("div", {
        id: "downloads-list",
        style: {
            display: "flex",
            flexDirection: "column",
            gap: "12px",
        },
    });
    container.appendChild(el("div", {
        style: { maxWidth: "700px", margin: "0 auto" },
        children: [
            el("div", {
                style: { display: "flex", gap: "10px", marginBottom: "20px" },
                children: [
                    el("input", {
                        id: "dl-url",
                        type: "text",
                        placeholder: "Enter URL to download...",
                        style: {
                            flex: 1,
                            padding: "14px",
                            border: "1px solid #ddd",
                            borderRadius: "10px",
                            fontSize: "1rem",
                        },
                    }),
                    el("select", {
                        id: "dl-priority",
                        style: {
                            padding: "14px",
                            border: "1px solid #ddd",
                            borderRadius: "10px",
                            fontSize: "0.95rem",
                        },
                        children: [
                            el("option", { value: "normal", textContent: "Normal" }),
                            el("option", { value: "high", textContent: "High" }),
                            el("option", { value: "low", textContent: "Low" }),
                        ],
                    }),
                    // More options toggle
                    el("button", {
                        id: "dl-more-toggle",
                        textContent: "More options ▾",
                        style: {
                            padding: "14px",
                            border: "1px solid #ddd",
                            borderRadius: "10px",
                            fontSize: "0.9rem",
                            background: "#f8f9fa",
                            cursor: "pointer",
                        },
                        onClick: () => {
                            const more = document.getElementById("dl-more-options");
                            if (more) {
                                const hidden = more.style.display === "none";
                                more.style.display = hidden ? "grid" : "none";
                            }
                        },
                    }),
                    btnPrimary("Add", async () => {
                        const input = document.getElementById("dl-url");
                        const priority = document.getElementById("dl-priority").value;
                        const url = input.value.trim();
                        if (!url)
                            return;
                        const cookies = document.getElementById("dl-cookies")?.value.trim() || undefined;
                        const cookiesFile = document.getElementById("dl-cookies-file")?.value.trim() || undefined;
                        const proxy = document.getElementById("dl-proxy")?.value.trim() || undefined;
                        const userAgent = document.getElementById("dl-user-agent")?.value.trim() || undefined;
                        const referer = document.getElementById("dl-referer")?.value.trim() || undefined;
                        const maxFilesize = document.getElementById("dl-max-filesize")?.value.trim();
                        const skipDownload = document.getElementById("dl-skip-download")?.checked;
                        try {
                            const res = await api.createAdvancedDownload({
                                url,
                                priority: priority,
                                cookies,
                                cookies_file: cookiesFile,
                                proxy,
                                user_agent: userAgent,
                                referer,
                                max_filesize: maxFilesize ? parseInt(maxFilesize, 10) : undefined,
                                skip_download: skipDownload || false,
                            });
                            if (res.ok && res.data) {
                                input.value = "";
                                haptic("success");
                                loadDownloads();
                            }
                            else {
                                showAlert(res.error || "Failed to add download");
                            }
                        }
                        catch (err) {
                            showAlert(err.message || "Error adding download");
                        }
                    }),
                    // More options panel (hidden by default)
                    el("div", {
                        id: "dl-more-options",
                        style: {
                            display: "none",
                            gridTemplateColumns: "1fr 1fr",
                            gap: "10px",
                            width: "100%",
                        },
                        children: [
                            el("label", { textContent: "Cookies (Netscape format)", style: { fontSize: "0.8rem", color: "#666" } }),
                            el("label", { textContent: "Cookies file path", style: { fontSize: "0.8rem", color: "#666" } }),
                            el("textarea", {
                                id: "dl-cookies",
                                placeholder: "Paste cookies string...",
                                style: {
                                    padding: "10px",
                                    border: "1px solid #ddd",
                                    borderRadius: "8px",
                                    fontSize: "0.85rem",
                                    fontFamily: "monospace",
                                    resize: "vertical",
                                    minHeight: "70px",
                                },
                            }),
                            el("input", {
                                id: "dl-cookies-file",
                                type: "text",
                                placeholder: "/path/to/cookies.txt",
                                style: {
                                    padding: "10px",
                                    border: "1px solid #ddd",
                                    borderRadius: "8px",
                                    fontSize: "0.85rem",
                                },
                            }),
                            el("label", { textContent: "Proxy", style: { fontSize: "0.8rem", color: "#666" } }),
                            el("label", { textContent: "User-Agent", style: { fontSize: "0.8rem", color: "#666" } }),
                            el("input", {
                                id: "dl-proxy",
                                type: "text",
                                placeholder: "http://proxy:port",
                                style: {
                                    padding: "10px",
                                    border: "1px solid #ddd",
                                    borderRadius: "8px",
                                    fontSize: "0.85rem",
                                },
                            }),
                            el("input", {
                                id: "dl-user-agent",
                                type: "text",
                                placeholder: "Mozilla/5.0 ...",
                                style: {
                                    padding: "10px",
                                    border: "1px solid #ddd",
                                    borderRadius: "8px",
                                    fontSize: "0.85rem",
                                },
                            }),
                            el("label", { textContent: "Referer", style: { fontSize: "0.8rem", color: "#666" } }),
                            el("label", { textContent: "Max filesize (MB)", style: { fontSize: "0.8rem", color: "#666" } }),
                            el("input", {
                                id: "dl-referer",
                                type: "text",
                                placeholder: "https://example.com",
                                style: {
                                    padding: "10px",
                                    border: "1px solid #ddd",
                                    borderRadius: "8px",
                                    fontSize: "0.85rem",
                                },
                            }),
                            el("input", {
                                id: "dl-max-filesize",
                                type: "number",
                                placeholder: "e.g. 100",
                                style: {
                                    padding: "10px",
                                    border: "1px solid #ddd",
                                    borderRadius: "8px",
                                    fontSize: "0.85rem",
                                },
                            }),
                            el("label", { textContent: "Skip download (info only)", style: { fontSize: "0.8rem", color: "#666", gridColumn: "span 2" } }),
                            el("div", {
                                style: { gridColumn: "span 2", display: "flex", alignItems: "center", gap: "8px" },
                                children: [
                                    el("input", {
                                        id: "dl-skip-download",
                                        type: "checkbox",
                                        style: { width: "18px", height: "18px" },
                                    }),
                                    el("span", { textContent: "Extract info only without downloading the file" }),
                                ],
                            }),
                        ],
                    }),
                ],
            }),
            downloadsList,
        ],
    }));
    async function loadDownloads() {
        try {
            const res = await api.listAdvancedDownloads();
            clear(downloadsList);
            if (res.ok && res.data) {
                const downloads = res.data;
                if (downloads.length === 0) {
                    downloadsList.appendChild(renderEmptyState("⬇️", "No downloads yet", "Add a URL above to start downloading"));
                }
                else {
                    for (const d of downloads) {
                        downloadsList.appendChild(renderDownloadCard(d));
                    }
                }
            }
            else {
                downloadsList.appendChild(renderEmptyState("⚠️", "Failed to load downloads", res.error || "Unknown error"));
            }
        }
        catch (err) {
            downloadsList.appendChild(renderEmptyState("⚠️", "Failed to load downloads", err.message || "Unknown error"));
        }
    }
    loadDownloads();
    // Connect to WebSocket for real-time updates
    const userId = store.getState().user?.id || 1;
    api.wsConnect(userId);
    api.wsSubscribe("downloads");
    // WebSocket connection status indicator
    const wsStatusEl = document.getElementById("ws-status");
    const updateWsStatus = (connected) => {
        if (!wsStatusEl)
            return;
        const dot = wsStatusEl.querySelector(".ws-dot");
        const text = wsStatusEl.querySelector("span");
        if (connected) {
            wsStatusEl.className = "ws-status connected";
            if (dot) {
                dot.classList.remove("ws-dot");
                dot.classList.add("ws-dot");
            }
            if (text)
                text.textContent = "Realtime: Connected";
        }
        else {
            wsStatusEl.className = "ws-status disconnected";
            if (text)
                text.textContent = "Realtime: Disconnected";
        }
    };
    api.on("ws:open", () => updateWsStatus(true));
    api.on("ws:close", () => updateWsStatus(false));
    // Listen for WebSocket download updates - update individual cards in real-time
    api.on("ws:download_started", (data) => {
        haptic("light");
        loadDownloads();
    });
    api.on("ws:download_completed", (data) => {
        haptic("success");
        loadDownloads();
    });
    api.on("ws:download_failed", (data) => {
        haptic("error");
        loadDownloads();
    });
    api.on("ws:download_progress", (data) => {
        // Update individual card progress without full reload
        const { job_id, progress } = data;
        const card = document.querySelector(`[data-job-id="${job_id}"]`);
        if (card) {
            const progressBar = card.querySelector(".progress-bar-fill");
            const progressText = card.querySelector(".progress-text");
            if (progressBar)
                progressBar.style.width = `${progress}%`;
            if (progressText)
                progressText.textContent = `${progress}%`;
        }
    });
    // Cleanup WebSocket on page unload
    window.addEventListener("beforeunload", () => {
        api.wsDisconnect();
    });
    return { loadDownloads };
}
function renderDownloadCard(job) {
    const isDownloading = job.status === "downloading";
    const isPaused = job.status === "paused";
    const isQueued = job.status === "queued";
    const isCompleted = job.status === "completed";
    const isFailed = job.status === "failed";
    const isCancelled = job.status === "cancelled";
    // Determine progress text
    let progressText = `${job.progress}%`;
    if (isQueued)
        progressText = "Queued";
    else if (isPaused)
        progressText = "Paused";
    else if (isCompleted)
        progressText = "Completed";
    else if (isFailed)
        progressText = `Failed${job.error ? `: ${job.error}` : ""}`;
    else if (isCancelled)
        progressText = "Cancelled";
    // Determine border color based on status
    const borderColor = isFailed ? "#d63031" : isCompleted ? "#00b894" : isPaused ? "#ffd700" : "#f0f0f0";
    return el("div", {
        className: "download-card",
        "data-job-id": job.job_id,
        style: {
            background: "#fff",
            padding: "16px",
            borderRadius: "12px",
            boxShadow: "0 2px 10px rgba(0,0,0,0.05)",
            border: `1px solid ${borderColor}`,
        },
        children: [
            el("div", {
                style: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" },
                children: [
                    el("div", {
                        textContent: job.title || (isQueued ? "Queued..." : "Downloading..."),
                        style: { fontSize: "0.95rem", fontWeight: "700", color: "#1a1a2e" },
                    }),
                    statusBadge(job.status),
                ],
            }),
            el("div", {
                textContent: job.url,
                style: { fontSize: "0.8rem", color: "#666", marginBottom: "8px", wordBreak: "break-all" },
            }),
            el("div", {
                style: { marginBottom: "8px" },
                children: [
                    el("div", {
                        style: { display: "flex", justifyContent: "space-between", fontSize: "0.75rem", color: "#666", marginBottom: "4px" },
                        children: [
                            el("span", { textContent: "Progress" }),
                            el("span", {
                                className: "progress-text",
                                textContent: progressText,
                            }),
                        ],
                    }),
                    progressBar(job.progress, "progress-bar-fill"),
                ],
            }),
            isFailed && job.error && el("div", {
                style: {
                    background: "#fee2e2",
                    color: "#d63031",
                    padding: "8px 12px",
                    borderRadius: "8px",
                    fontSize: "0.8rem",
                    marginBottom: "8px",
                },
                textContent: `Error: ${job.error}`,
            }),
            job.retry_count && job.retry_count > 0 && el("div", {
                style: { fontSize: "0.75rem", color: "#666", marginBottom: "8px" },
                textContent: `Retry ${job.retry_count}/${job.max_retries || 3}`,
            }),
            el("div", {
                style: { display: "flex", gap: "6px", flexWrap: "wrap" },
                children: [
                    isDownloading && btnSecondary("Pause", async () => {
                        try {
                            await api.pauseDownload(job.job_id);
                            // Trigger refresh via parent
                        }
                        catch (err) {
                            showAlert(err.message || "Failed to pause");
                        }
                    }),
                    isPaused && btnSecondary("Resume", async () => {
                        try {
                            await api.resumeDownload(job.job_id);
                        }
                        catch (err) {
                            showAlert(err.message || "Failed to resume");
                        }
                    }),
                    (isQueued || isDownloading || isPaused) && btnSecondary("Cancel", async () => {
                        try {
                            await api.cancelDownload(job.job_id);
                        }
                        catch (err) {
                            showAlert(err.message || "Failed to cancel");
                        }
                    }, true),
                    isFailed && btnSecondary("Retry", async () => {
                        try {
                            // Re-create the download
                            await api.createAdvancedDownload({
                                url: job.url,
                                source: job.source,
                                priority: job.priority,
                                cookies: job.cookies || undefined,
                                cookies_file: job.cookies_file || undefined,
                                proxy: job.proxy || undefined,
                                user_agent: job.user_agent || undefined,
                                referer: job.referer || undefined,
                                max_filesize: job.max_filesize || undefined,
                                skip_download: job.skip_download || false,
                            });
                        }
                        catch (err) {
                            showAlert(err.message || "Failed to retry");
                        }
                    }),
                    isCompleted && btnSecondary("Done", () => {
                        haptic("success");
                    }),
                ],
            }),
        ],
    });
}
// ---- Settings Screen ----
async function renderSettings(container) {
    clear(container);
    const s = store;
    container.appendChild(el("h2", {
        textContent: "Settings",
        style: { marginBottom: "24px", color: "#1a1a2e" },
    }));
    const sections = el("div", {
        style: { display: "flex", flexDirection: "column", gap: "24px" },
    });
    // Theme
    sections.appendChild(renderSettingSection("Appearance", [
        renderSettingRow("Theme", () => {
            const current = s.getState().theme;
            const themes = ["light", "dark", "system"];
            const idx = themes.indexOf(current);
            const next = themes[(idx + 1) % themes.length];
            s.setState({ theme: next });
            localStorage.setItem("videl_theme", next);
            applyTheme(next);
        }, `Current: ${s.getState().theme}`),
    ]));
    // Language
    sections.appendChild(renderSettingSection("Language", [
        renderSettingRow("Language", () => {
            const langs = ["en", "es", "fr", "zh"];
            const current = s.getState().language;
            const idx = langs.indexOf(current);
            const next = langs[(idx + 1) % langs.length];
            s.setState({ language: next });
            localStorage.setItem("videl_language", next);
        }, `Current: ${s.getState().language}`),
    ]));
    // Notifications
    sections.appendChild(renderSettingSection("Notifications", [
        renderSettingToggle("Download Complete", s.getState().user?.notifications ?? true, async (checked) => {
            s.setState({ user: { ...s.getState().user, notifications: checked } });
            await api.setNotificationPrefs({ download_complete: checked });
        }),
        renderSettingToggle("Payment Received", true, async (checked) => {
            await api.setNotificationPrefs({ payment_received: checked });
        }),
        renderSettingToggle("System Alerts", false, async (checked) => {
            await api.setNotificationPrefs({ system_alerts: checked });
        }),
    ]));
    // Download Preferences
    sections.appendChild(renderSettingSection("Downloads", [
        renderSettingRow("Max Concurrent Downloads", async () => {
            const current = s.getState().user?.max_concurrent_downloads || 3;
            const next = current === 3 ? 5 : current === 5 ? 10 : 3;
            s.setState({ user: { ...s.getState().user, max_concurrent_downloads: next } });
            try {
                await api.createAdvancedDownload({ url: "", priority: "normal" });
            }
            catch { }
        }, `Current: ${s.getState().user?.max_concurrent_downloads || 3}`),
        renderSettingRow("Default Format", () => {
            const formats = ["mp3", "m4a", "flac", "wav"];
            const current = s.getState().user?.default_format || "mp3";
            const idx = formats.indexOf(current);
            const next = formats[(idx + 1) % formats.length];
            s.setState({ user: { ...s.getState().user, default_format: next } });
        }, `Current: ${s.getState().user?.default_format || "mp3"}`),
    ]));
    // API Key Management
    sections.appendChild(renderSettingSection("API Keys", [
        renderSettingRow("View All Keys", () => {
            s.setCurrentView("dashboard");
        }, "Manage your API keys"),
        renderSettingRow("Rate Limit Status", async () => {
            try {
                const keysRes = await api.listKeys();
                if (keysRes.ok && keysRes.data) {
                    const keys = keysRes.data.keys || [];
                    if (keys.length > 0) {
                        const key = keys[0];
                        const res = await api.getKeyRateLimit(key.key_id || key.key_prefix);
                        if (res.ok) {
                            const rl = res.data;
                            showAlert(`Rate Limit:\nLimit: ${rl.limit} req/min\nRemaining: ${rl.remaining}\nReset in: ${rl.reset_after_seconds}s`);
                        }
                    }
                }
            }
            catch (err) {
                showAlert(err.message || "Failed to get rate limit");
            }
        }, "Check current rate limit"),
    ]));
    container.appendChild(el("div", {
        style: { maxWidth: "600px", margin: "0 auto" },
        children: [
            el("h2", { textContent: "Settings", style: { marginBottom: "24px", color: "#1a1a2e" } }),
            sections,
        ],
    }));
}
function renderSettingSection(title, rows) {
    return el("div", {
        className: "card",
        style: {
            background: "#fff",
            borderRadius: "16px",
            boxShadow: "0 2px 10px rgba(0,0,0,0.05)",
            border: "1px solid #f0f0f0",
            padding: "20px",
        },
        children: [
            el("h3", {
                textContent: title,
                style: { margin: "0 0 16px 0", color: "#1a1a2e", fontSize: "1.1rem" },
            }),
            el("div", {
                style: { display: "flex", flexDirection: "column", gap: "12px" },
                children: rows,
            }),
        ],
    });
}
function renderSettingRow(title, onClick, subtitle) {
    return el("div", {
        style: {
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "12px 0",
            borderBottom: "1px solid #f0f0f0",
        },
        children: [
            el("div", {
                children: [
                    el("div", { textContent: title, style: { fontWeight: "600", color: "#1a1a2e" } }),
                    el("div", { textContent: subtitle, style: { fontSize: "0.85rem", color: "#666" } }),
                ],
            }),
            el("button", {
                textContent: "Change",
                style: {
                    padding: "6px 14px",
                    background: "#f3f4f6",
                    border: "none",
                    borderRadius: "6px",
                    fontWeight: "600",
                    cursor: "pointer",
                },
                onClick: () => {
                    haptic("light");
                    onClick();
                },
            }),
        ],
    });
}
function renderSettingToggle(title, checked, onChange) {
    return el("div", {
        style: {
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "12px 0",
            borderBottom: "1px solid #f0f0f0",
        },
        children: [
            el("div", { textContent: title, style: { fontWeight: "600", color: "#1a1a2e" } }),
            el("label", {
                style: {
                    position: "relative",
                    display: "inline-block",
                    width: "44px",
                    height: "24px",
                },
                children: [
                    el("input", {
                        type: "checkbox",
                        checked,
                        style: { opacity: 0, width: 0, height: 0 },
                        onChange: (e) => {
                            haptic("selection");
                            onChange(e.target.checked);
                        },
                    }),
                    el("span", {
                        style: {
                            position: "absolute",
                            top: 2,
                            left: 2,
                            width: 20,
                            height: 20,
                            background: checked ? "#0088cc" : "#ccc",
                            borderRadius: "50%",
                            transition: "all 0.2s ease",
                        },
                    }),
                ],
            }),
        ],
    });
}
function applyTheme(theme) {
    if (theme === "dark" || (theme === "system" && window.matchMedia?.("(prefers-color-scheme: dark)").matches)) {
        document.documentElement.setAttribute("data-theme", "dark");
    }
    else {
        document.documentElement.removeAttribute("data-theme");
    }
}
// ---- Admin Screen ----
async function renderAdmin(container) {
    clear(container);
    container.appendChild(el("h2", {
        textContent: "Admin Panel",
        style: { marginBottom: "24px", color: "#1a1a2e" },
    }));
    const grid = el("div", {
        style: {
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
            gap: "16px",
            marginBottom: "32px",
        },
    });
    const adminActions = [
        { title: "Users", desc: "Manage all users", onClick: () => { showAlert("User management coming soon"); } },
        { title: "Stats", desc: "Global statistics", onClick: async () => {
                const res = await api.getGlobalStats();
                if (res.ok) {
                    const data = res.data;
                    showAlert(`Total Users: ${data.total_users}\nRequests Today: ${data.total_requests_today}\nDownloads: ${data.total_downloads_today}`);
                }
            } },
        { title: "Webhooks", desc: "Manage webhooks", onClick: () => { showAlert("Webhook management coming soon"); } },
        { title: "Maintenance", desc: "Toggle maintenance mode", onClick: () => { showAlert("Maintenance toggle coming soon"); } },
    ];
    for (const action of adminActions) {
        grid.appendChild(el("div", {
            className: "card",
            style: {
                background: "#fff",
                padding: "20px",
                borderRadius: "12px",
                boxShadow: "0 2px 10px rgba(0,0,0,0.05)",
                border: "1px solid #f0f0f0",
                cursor: "pointer",
            },
            onClick: action.onClick,
            children: [
                el("div", { textContent: action.title, style: { fontWeight: "700", color: "#1a1a2e", marginBottom: "4px" } }),
                el("div", { textContent: action.desc, style: { fontSize: "0.85rem", color: "#666" } }),
            ],
        }));
    }
    container.appendChild(el("div", {
        style: { maxWidth: "800px", margin: "0 auto" },
        children: [el("h2", { textContent: "Admin Panel", style: { marginBottom: "24px", color: "#1a1a2e" } }), grid],
    }));
}
/**
 * Main Application - TypeScript
 * Videl-Api WebApp entry point with routing and layout
 */
// Navigation state
let currentUser = null;
let currentView = "auth";
// DOM elements
const app = document.getElementById("app");
if (!app) {
    throw new Error("App container not found");
}
function nav(view) {
    currentView = view;
    store.setCurrentView(view);
    render();
}
function getMainButtonLabel(view) {
    switch (view) {
        case "auth": return "Sign in";
        case "dashboard": return "Create Key";
        case "search": return "Search";
        case "downloads": return "Add Download";
        case "settings": return "Sync";
        case "admin": return "Refresh";
        default: return "Menu";
    }
}
async function render() {
    clear(app);
    const s = store;
    // Apply theme
    applyTheme(s.getState().theme);
    // Top navigation bar
    const navBar = el("div", {
        style: {
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            height: isTelegramWebApp() ? "76px" : "56px",
            background: getComputedStyle(document.documentElement).getPropertyValue("--bg-header") || "#fff",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: isTelegramWebApp() ? "8px 16px" : "12px 20px",
            zIndex: "100",
            boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
        },
    });
    // Logo / title
    const logo = el("div", {
        style: {
            display: "flex",
            alignItems: "center",
            gap: "8px",
            fontSize: "1.2rem",
            fontWeight: "800",
            color: getComputedStyle(document.documentElement).getPropertyValue("--text-primary") || "#1a1a2e",
        },
        children: [
            el("span", { textContent: "V" }),
            el("span", { textContent: "idel-Api" }),
        ],
        onClick: () => nav("dashboard"),
    });
    // User avatar (shown when logged in)
    const userBadge = currentUser?.photo_url
        ? el("img", {
            src: currentUser.photo_url,
            alt: "avatar",
            style: { width: "32px", height: "32px", borderRadius: "50%", border: "2px solid #fff", boxShadow: "0 2px 4px rgba(0,0,0,0.2)" },
        })
        : null;
    // Main button (Telegram native)
    if (tg) {
        tg.MainButton.setText(getMainButtonLabel(view));
        tg.MainButton.show();
        tg.SecondaryButton.hide();
        tg.BackButton.hide();
        tg.MainButton.onClick(() => {
            haptic("light");
            if (view === "auth") {
                nav("dashboard");
            }
            else if (view === "dashboard") {
                s.openModal("create-key");
            }
            else if (view === "search") {
                // Focus search input
                const input = document.getElementById("search-input");
                input?.focus();
            }
            else if (view === "downloads") {
                const input = document.getElementById("dl-url");
                input?.focus();
            }
            else if (view === "settings") {
                nav("settings");
            }
            else if (view === "admin") {
                nav("admin");
            }
        });
    }
    // Content area
    const content = el("div", {
        style: {
            paddingTop: isTelegramWebApp() ? "92px" : "72px",
            padding: "16px",
            minHeight: "100vh",
            boxSizing: "border-box",
        },
    });
    app.appendChild(navBar);
    app.appendChild(content);
    // Render view
    switch (view) {
        case "auth":
            renderAuthScreen(content, (user) => {
                currentUser = user;
                store.setUser(user, s.getState().token || "");
                nav("dashboard");
            });
            break;
        case "dashboard":
            if (!currentUser) {
                content.appendChild(renderEmptyState("🔐", "Please sign in", "Sign in with Telegram to access your dashboard", {
                    text: "Sign in",
                    onClick: () => nav("auth"),
                }));
            }
            else {
                await renderDashboard(content, currentUser);
            }
            break;
        case "search":
            if (!currentUser) {
                content.appendChild(renderEmptyState("🔐", "Please sign in", "Sign in with Telegram to use search", {
                    text: "Sign in",
                    onClick: () => nav("auth"),
                }));
            }
            else {
                await renderSearch(content);
            }
            break;
        case "downloads":
            if (!currentUser) {
                content.appendChild(renderEmptyState("🔐", "Please sign in", "Sign in with Telegram to manage downloads", {
                    text: "Sign in",
                    onClick: () => nav("auth"),
                }));
            }
            else {
                await renderDownloads(content);
            }
            break;
        case "settings":
            if (!currentUser) {
                content.appendChild(renderEmptyState("🔐", "Please sign in", "Sign in with Telegram to access settings", {
                    text: "Sign in",
                    onClick: () => nav("auth"),
                }));
            }
            else {
                await renderSettings(content);
            }
            break;
        case "admin":
            if (!currentUser || currentUser.tier !== "owner") {
                content.appendChild(renderEmptyState("🔒", "Admin access required", "Owner tier required for admin panel"));
            }
            else {
                await renderAdmin(content);
            }
            break;
        default:
            content.appendChild(renderEmptyState("❓", "Unknown view", `View "${view}" not found`));
            break;
    }
    // Reload keys listener
    window.removeEventListener("reload-keys", handleReloadKeys);
    window.addEventListener("reload-keys", handleReloadKeys);
}
function handleReloadKeys() {
    if (currentView === "dashboard" && currentUser) {
        renderDashboard(document.getElementById("app").children[1], currentUser);
    }
}
// Initialize
function init() {
    store.loadPersisted();
    applyTheme(store.getState().theme);
    // Handle Telegram init data
    if (isTelegramWebApp()) {
        const user = window.Telegram?.WebApp?.initDataUnsafe?.user;
        if (user) {
            currentUser = user;
            store.setUser(user);
            nav("dashboard");
        }
        else {
            nav("auth");
        }
        initWebApp();
    }
    else {
        // Not in Telegram - show a notice but still allow usage
        nav("auth");
    }
    // Online/offline detection
    window.addEventListener("online", () => {
        store.setOnline(true);
        haptic("success");
    });
    window.addEventListener("offline", () => {
        store.setOnline(false);
        haptic("error");
    });
    // Theme change listener
    window.matchMedia?.("(prefers-color-scheme: dark)").addEventListener("change", () => {
        if (store.getState().theme === "system") {
            applyTheme("system");
        }
    });
}
init();
{ nav, currentUser };
