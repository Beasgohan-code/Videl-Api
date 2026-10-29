/**
 * Videl-Api Telegram WebApp
 * Richgram-style UI (Badmunda05 pattern) with inline updates, no spam
 * Works both inside Telegram WebApp and as a regular web page
 */

// ---------------------------------------------------------------------------
// Telegram WebApp SDK wrapper
// ---------------------------------------------------------------------------

const tg = window.Telegram?.WebApp || window.tg?.WebApp;

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
        // Remove any existing click handlers before adding new ones
        tg.MainButton.off("click");
        tg.MainButton.on("click", () => {
            if (currentView === "dashboard") {
                openCreateKeyModal();
            }
        });
    }
}

function haptic(type) {
    if (!tg) return;
    try {
        if (type === "success") tg.HapticFeedback.notificationOccurred("success");
        else if (type === "error") tg.HapticFeedback.notificationOccurred("error");
        else if (type === "warning") tg.HapticFeedback.notificationOccurred("warning");
        else if (type === "selection") tg.HapticFeedback.selectionChanged();
        else tg.HapticFeedback.impactOccurred(type);
    } catch { }
}

// Inline UI notifications instead of spam alerts
function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = "0";
        setTimeout(() => toast.remove(), 300);
    }, 3000);
    haptic(type === "error" ? "error" : type === "success" ? "success" : "selection");
}

function showAlert(message) {
    // Use inline toast instead of blocking alert (no spam)
    showToast(message, "info");
    if (tg) tg?.showAlert(message);
}

function showConfirm(message, callback) {
    if (tg) {
        tg?.showConfirm(message, (confirmed) => callback(confirmed));
    } else {
        if (confirm(message)) callback(true);
        else callback(false);
    }
}

function showPopup(params, callback) {
    if (tg) tg?.showPopup(params, callback);
}

// ---------------------------------------------------------------------------
// API Client
// ---------------------------------------------------------------------------

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
        localStorage.setItem("videl_token", token);
    }
    clearToken() {
        this.token = null;
        localStorage.removeItem("videl_token");
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
        } catch (err) {
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
        return this.request("/v1/oauth/token", {
            method: "POST",
            body: JSON.stringify({ client_id: clientId, client_secret: clientSecret, scope }),
        });
    }
    // ---------- Keys ----------
    async listKeys() {
        return this.request("/v1/web/keys/list");
    }
    async getKey(keyId) {
        return this.request(`/v1/web/keys/${keyId}`);
    }
    async createKey(payload) {
        return this.request("/v1/web/keys/create", {
            method: "POST",
            body: JSON.stringify(payload),
        });
    }
    async revokeKey(keyId) {
        return this.request(`/v1/web/keys/${keyId}`, {
            method: "DELETE",
        });
    }
    async rotateKey(keyId) {
        return this.request(`/v1/web/keys/${keyId}/rotate`, {
            method: "PATCH",
        });
    }
    async patchKey(keyId, payload) {
        return this.request(`/v1/web/keys/${keyId}`, {
            method: "PATCH",
            body: JSON.stringify(payload),
        });
    }
    // ---------- Stats ----------
    async getStats() {
        return this.request("/v1/web/stats");
    }
    async getOwnerKeys() {
        return this.request("/v1/web/owner/keys");
    }
    // ---------- Sources ----------
    async getSources() {
        return this.request("/v1/sources");
    }
    // ---------- Search ----------
    async searchMusic(query, source = "youtube", limit = 10) {
        return this.request(`/v1/search?q=${encodeURIComponent(query)}&source=${source}&limit=${limit}`);
    }
    // ---------- Downloads ----------
    async createAdvancedDownload(payload) {
        return this.request("/v1/downloads/advanced", {
            method: "POST",
            body: JSON.stringify(payload),
        });
    }
    async listAdvancedDownloads() {
        return this.request("/v1/downloads");
    }
    async cancelDownload(jobId) {
        return this.request(`/v1/downloads/${jobId}/cancel`, {
            method: "POST",
        });
    }
    async retryDownload(jobId) {
        return this.request(`/v1/downloads/${jobId}/retry`, {
            method: "POST",
        });
    }
    // ---------- Settings ----------
    async setNotificationPrefs(prefs) {
        return this.request("/v1/notifications/preferences", {
            method: "PUT",
            body: JSON.stringify(prefs),
        });
    }
    async setRateLimit(limit, period) {
        return this.request("/v1/settings/rate-limit", {
            method: "PUT",
            body: JSON.stringify({ limit, period }),
        });
    }
}

const api = new ApiClient();

// ---------------------------------------------------------------------------
// State Store
// ---------------------------------------------------------------------------

const defaultState = {
    user: null,
    token: null,
    keys: [],
    stats: null,
    sources: [],
    downloads: [],
    favorites: [],
    playlists: [],
    notifications: [],
    activityFeed: [],
    currentView: "auth",
    theme: "system",
    isOnline: true,
    wsConnected: false,
    modals: {},
};

class Store {
    constructor() {
        this.state = { ...defaultState };
        this.listeners = new Set();
    }
    subscribe(listener) {
        this.listeners.add(listener);
        return () => { this.listeners.delete(listener); };
    }
    getState() {
        return this.state;
    }
    setState(partial) {
        this.state = { ...this.state, ...partial };
        this.listeners.forEach((l) => l());
    }
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
        if (token) localStorage.setItem("videl_token", token);
        else localStorage.removeItem("videl_token");
        api.setToken(token);
    }
    setKeys(keys) { this.setState({ keys }); }
    setStats(stats) { this.setState({ stats }); }
    setSources(sources) { this.setState({ sources }); }
    setDownloads(downloads) { this.setState({ downloads }); }
    setFavorites(favorites) { this.setState({ favorites }); }
    setPlaylists(playlists) { this.setState({ playlists }); }
    setNotifications(notifications) { this.setState({ notifications }); }
    setActivityFeed(feed) { this.setState({ activityFeed: feed }); }
    setCurrentView(view) { this.setState({ currentView: view }); }
    setWsConnected(connected) { this.setState({ wsConnected: connected }); }
    setOnline(online) { this.setState({ isOnline: online }); }
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
            api.setToken(token);
        }
        const theme = localStorage.getItem("videl_theme");
        if (theme) this.state.theme = theme;
        const lang = localStorage.getItem("videl_language");
        if (lang) this.state.language = lang;
    }
}

const store = new Store();

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------

function el(tag, props = {}, children = []) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
        if (k === "className") e.className = v;
        else if (k === "innerHTML") e.innerHTML = v;
        else if (k === "textContent") e.textContent = v;
        else if (k.startsWith("on") && typeof v === "function") {
            e.addEventListener(k.slice(2).toLowerCase(), v);
        } else if (k === "style" && typeof v === "object") {
            Object.assign(e.style, v);
        } else {
            e.setAttribute(k, v);
        }
    }
    children.forEach((c) => {
        if (c) e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return e;
}

function clear(container) {
    container.innerHTML = "";
}

function formatBytes(bytes) {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

function formatNumber(n) {
    return n.toLocaleString();
}

function formatDuration(seconds) {
    if (!seconds) return "--";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return h > 0 ? `${h}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}` : `${m}:${s.toString().padStart(2, "0")}`;
}

function formatDate(iso) {
    if (!iso) return "--";
    try {
        return new Date(iso).toLocaleString();
    } catch { return "--"; }
}

function tierColor(tier) {
    const colors = { free: "#666", pro: "#0088cc", owner: "#d63031" };
    return colors[tier] || "#666";
}

function tierBadge(tier) {
    const labels = { free: "Free", pro: "Pro", owner: "Owner" };
    return el("span", {
        style: {
            display: "inline-block",
            padding: "2px 8px",
            borderRadius: "10px",
            background: tierColor(tier) + "20",
            color: tierColor(tier),
            fontSize: "12px",
            fontWeight: "700",
        },
        textContent: labels[tier] || tier,
    });
}

function statusBadge(status) {
    const colors = { completed: "#00b894", failed: "#d63031", downloading: "#0088cc", queued: "#fdcb6e" };
    return el("span", {
        style: {
            display: "inline-block",
            padding: "2px 8px",
            borderRadius: "10px",
            background: (colors[status] || "#666") + "20",
            color: colors[status] || "#666",
            fontSize: "12px",
            fontWeight: "700",
        },
        textContent: status,
    });
}

function progressBar(progress, fillClass = "fill-primary") {
    return el("div", {
        className: "progress-bar",
        style: { height: "8px", borderRadius: "4px", background: "#eaeaea", overflow: "hidden" },
        children: [
            el("div", {
                className: fillClass,
                style: { height: "100%", width: progress + "%", background: "#0088cc", transition: "width 0.3s" },
            }),
        ],
    });
}

function renderPageHeader(title, subtitle) {
    return el("div", {
        style: { marginBottom: "24px" },
        children: [
            el("h2", { style: { margin: 0, fontSize: "1.5rem", fontWeight: "800" }, textContent: title }),
            subtitle && el("p", { style: { margin: "4px 0 0", color: "#666", fontSize: "0.95rem" }, textContent: subtitle }),
        ].filter(Boolean),
    });
}

function renderCard(children, style) {
    return el("div", {
        style: {
            background: "#fff",
            borderRadius: "16px",
            padding: "20px",
            boxShadow: "0 4px 20px rgba(0,0,0,0.06)",
            ...style,
        },
        children,
    });
}

function renderStatCard(label, value, color, icon) {
    return el("div", {
        style: {
            background: "linear-gradient(135deg, #fff, #f8f9fa)",
            border: "1px solid #eaeaea",
            borderRadius: "16px",
            padding: "16px",
            textAlign: "center",
        },
        children: [
            el("div", { style: { fontSize: "2rem", marginBottom: "8px" }, textContent: icon || "" }),
            el("div", { style: { fontSize: "1.5rem", fontWeight: "800", color: color || "#1a1a2e" }, textContent: value }),
            el("div", { style: { fontSize: "0.85rem", color: "#666", marginTop: "4px" }, textContent: label }),
        ],
    });
}

function renderEmptyState(icon, title, subtitle, action) {
    const children = [
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
            textContent: icon,
        }),
        el("h2", { style: { marginBottom: "8px", fontSize: "1.25rem", fontWeight: "800" }, textContent: title }),
        el("p", { style: { color: "#666", marginBottom: "32px", fontSize: "1.1rem", textAlign: "center" }, textContent: subtitle }),
    ];
    if (action) {
        children.push(el("button", {
            style: {
                background: "linear-gradient(135deg, #0088cc, #005588)",
                color: "#fff",
                border: "none",
                padding: "12px 24px",
                borderRadius: "12px",
                fontSize: "1rem",
                fontWeight: "700",
                cursor: "pointer",
            },
            textContent: action.text,
            onClick: action.onClick,
        }));
    }
    return el("div", {
        style: {
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            padding: "60px 20px",
            textAlign: "center",
        },
        children,
    });
}

function renderLoading(container) {
    clear(container);
    container.appendChild(el("div", {
        style: {
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            padding: "60px 20px",
        },
        children: [
            el("div", {
                style: {
                    width: "40px",
                    height: "40px",
                    border: "3px solid #eaeaea",
                    borderTop: "3px solid #0088cc",
                    borderRadius: "50%",
                    animation: "spin 1s linear infinite",
                },
            }),
            el("p", { style: { marginTop: "16px", color: "#666" }, textContent: "Loading..." }),
        ],
    }));
}

// ---------------------------------------------------------------------------
// Theme
// ---------------------------------------------------------------------------

function applyTheme(theme) {
    if (theme === "dark" || (theme === "system" && window.matchMedia?.("(prefers-color-scheme: dark)").matches)) {
        document.documentElement.setAttribute("data-theme", "dark");
    } else {
        document.documentElement.removeAttribute("data-theme");
    }
}

// ---------------------------------------------------------------------------
// Admin Screen
// ---------------------------------------------------------------------------

async function renderAdmin(container) {
    clear(container);
    container.appendChild(renderPageHeader("Admin Panel", "Owner-only management"));
    const grid = el("div", {
        style: {
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
            gap: "16px",
        },
    });

    const adminCards = [
        { title: "Users", desc: "View all registered users", icon: "👥", color: "#0088cc", action: () => { showToast("User management: use /users in bot"); } },
        { title: "Stats", desc: "Bot statistics overview", icon: "📊", color: "#00b894", action: async () => {
            const res = await api.getStats();
            if (res.ok) {
                const d = res.data;
                showToast(`Total Users: ${d.total_users || 0} | Downloads: ${d.total_downloads || 0}`, "success");
            } else {
                showToast("Failed to load stats", "error");
            }
        } },
        { title: "Broadcast", desc: "Send message to all users", icon: "📢", color: "#fdcb6e", action: () => { showToast("Use /broadcast in bot"); } },
        { title: "All Keys", desc: "View every API key", icon: "🔑", color: "#6c5ce7", action: async () => {
            const res = await api.getOwnerKeys();
            if (res.ok) {
                showToast(`Total keys: ${res.data.keys?.length || 0}`, "success");
            } else {
                showToast("Failed to load keys", "error");
            }
        } },
        { title: "System", desc: "System health status", icon: "⚙️", color: "#6c5ce7", action: async () => {
            showToast("Check /status in bot", "info");
        } },
        { title: "Webhooks", desc: "Manage webhooks", icon: "🔗", color: "#666", action: () => { showToast("Webhook management via API"); } },
        { title: "Maintenance", desc: "Toggle maintenance mode", icon: "🔧", color: "#666", action: () => { showToast("Maintenance toggle via API"); } },
    ];

    adminCards.forEach((card) => {
        grid.appendChild(el("div", {
            style: {
                background: "#fff",
                border: "1px solid #eaeaea",
                borderRadius: "16px",
                padding: "20px",
                cursor: "pointer",
                transition: "transform 0.2s, box-shadow 0.2s",
            },
            children: [
                el("div", { style: { fontSize: "2rem", marginBottom: "12px" }, textContent: card.icon }),
                el("h3", { style: { margin: "0 0 8px", fontSize: "1.1rem", fontWeight: "800" }, textContent: card.title }),
                el("p", { style: { color: "#666", fontSize: "0.9rem", margin: 0 }, textContent: card.desc }),
            ],
            onClick: card.action,
        }));
    });

    container.appendChild(grid);
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

async function renderDashboard(container, user) {
    clear(container);
    container.appendChild(renderPageHeader("Dashboard", `Welcome back, ${user.first_name || user.username || "User"}`));

    // Stats row
    const statsRow = el("div", {
        style: {
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
            gap: "16px",
            marginBottom: "24px",
        },
    });

    try {
        const statsRes = await api.getStats();
        const keysRes = await api.listKeys();

        const stats = statsRes.ok ? statsRes.data : {};
        const keys = keysRes.ok ? keysRes.data : [];

        const tierColorMap = { free: "#666", pro: "#0088cc", owner: "#d63031" };
        const userTier = user.tier || "free";

        statsRow.appendChild(renderStatCard("Tier", userTier.charAt(0).toUpperCase() + userTier.slice(1), tierColorMap[userTier] || "#666", user.tier === "owner" ? "👑" : user.tier === "pro" ? "💎" : "🆓"));
        statsRow.appendChild(renderStatCard("API Keys", keys.length || 0, "#0088cc", "🔑"));
        statsRow.appendChild(renderStatCard("Requests Today", stats.requests_today || 0, "#00b894", "🔍"));
        statsRow.appendChild(renderStatCard("Downloads", stats.downloads_today || 0, "#fdcb6e", "⬇️"));
    } catch (e) {
        statsRow.appendChild(renderStatCard("Tier", (user.tier || "free").charAt(0).toUpperCase() + (user.tier || "free").slice(1), "#666", "🆓"));
        statsRow.appendChild(renderStatCard("API Keys", "0", "#0088cc", "🔑"));
        statsRow.appendChild(renderStatCard("Requests Today", "0", "#00b894", "🔍"));
        statsRow.appendChild(renderStatCard("Downloads", "0", "#fdcb6e", "⬇️"));
    }

    container.appendChild(statsRow);

    // Quick actions
    const actionsRow = el("div", {
        style: {
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
            gap: "16px",
            marginBottom: "24px",
        },
    });

    const actions = [
        { title: "Create Key", icon: "🔑", color: "#0088cc", action: openCreateKeyModal },
        { title: "Search", icon: "🔍", color: "#00b894", action: () => nav("search") },
        { title: "Downloads", icon: "⬇️", color: "#fdcb6e", action: () => nav("downloads") },
        { title: "Settings", icon: "⚙️", color: "#6c5ce7", action: () => nav("settings") },
    ];

    actions.forEach((a) => {
        actionsRow.appendChild(el("button", {
            style: {
                background: "#fff",
                border: "1px solid #eaeaea",
                borderRadius: "16px",
                padding: "20px",
                cursor: "pointer",
                transition: "transform 0.2s",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
            },
            children: [
                el("div", { style: { fontSize: "2rem", marginBottom: "10px" }, textContent: a.icon }),
                el("div", { style: { fontWeight: "700", fontSize: "1rem" }, textContent: a.title }),
            ],
            onClick: a.action,
        }));
    });

    container.appendChild(actionsRow);

    // Recent keys section
    const keysSection = el("div", {
        style: { marginTop: "32px" },
        children: [
            el("div", {
                style: {
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: "16px",
                },
                children: [
                    el("h3", { style: { margin: 0, fontSize: "1.1rem", fontWeight: "800" }, textContent: "Recent API Keys" }),
                    el("button", {
                        style: {
                            background: "linear-gradient(135deg, #0088cc, #005588)",
                            color: "#fff",
                            border: "none",
                            padding: "10px 20px",
                            borderRadius: "12px",
                            fontWeight: "700",
                            cursor: "pointer",
                        },
                        textContent: "Create Key",
                        onClick: openCreateKeyModal,
                    }),
                ],
            }),
            el("div", {
                id: "keys-list",
                style: {
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
                    gap: "12px",
                },
            }),
        ],
    });

    container.appendChild(keysSection);

    // Load keys
    const keysList = document.getElementById("keys-list");
    try {
        const res = await api.listKeys();
        const keyList = res.ok ? res.data : [];
        if (keyList.length === 0) {
            keysList.appendChild(renderEmptyState("🔑", "No API keys yet", "Create your first key to access the API", {
                text: "Create Key",
                onClick: openCreateKeyModal,
            }));
        } else {
            keyList.innerHTML = "";
            keyList.slice(0, 5).forEach((k) => {
                keysList.appendChild(renderKeyCard(k));
            });
        }
    } catch (e) {
        keysList.appendChild(renderEmptyState("⚠️", "Failed to load keys", e.message || "Unknown error"));
    }
}

// ---------------------------------------------------------------------------
// Key Card
// ---------------------------------------------------------------------------

function renderKeyCard(k) {
    const tier = k.tier || "free";
    const active = k.active !== false;
    return el("div", {
        style: {
            background: "#fff",
            border: `1px solid ${active ? "#eaeaea" : "#d6303130"}`,
            borderRadius: "16px",
            padding: "16px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
        },
        children: [
            el("div", {
                children: [
                    el("div", { style: { fontWeight: "700", fontSize: "0.9rem", marginBottom: "6px", wordBreak: "break-all" }, textContent: k.key_prefix || "videl_" }),
                    el("div", { style: { fontSize: "0.85rem", color: "#666" }, textContent: `Tier: ${tier}  •  ${active ? "Active" : "Inactive"}` }),
                ],
            }),
            el("div", {
                style: {
                    display: "flex",
                    gap: "8px",
                },
                children: [
                    el("button", {
                        style: {
                            background: "#f8f9fa",
                            border: "1px solid #eaeaea",
                            borderRadius: "10px",
                            padding: "8px 12px",
                            fontSize: "0.85rem",
                            cursor: "pointer",
                        },
                        textContent: "Rotate",
                        onClick: async () => {
                            const res = await api.rotateKey(k.key_id);
                            if (res.ok) {
                                showToast("Key rotated successfully", "success");
                                // Inline update - no page reload
                                const btn = document.getElementById(`btn-rotate-${k.key_id}`);
                                if (btn) btn.textContent = "Rotated!";
                                setTimeout(() => nav("dashboard"), 1500);
                            } else {
                                showToast(res.error || "Failed to rotate key", "error");
                            }
                        },
                    }),
                    el("button", {
                        style: {
                            background: "#fff",
                            border: "1px solid #d63031",
                            color: "#d63031",
                            borderRadius: "10px",
                            padding: "8px 12px",
                            fontSize: "0.85rem",
                            cursor: "pointer",
                        },
                        textContent: "Revoke",
                        onClick: async () => {
                            const ok = await new Promise((resolve) => showConfirm("Revoke this API key?", resolve));
                            if (ok) {
                                const res = await api.revokeKey(k.key_id);
                                if (res.ok) {
                                    showToast("Key revoked", "success");
                                    // Remove card inline
                                    const card = document.getElementById(`key-card-${k.key_id}`);
                                    if (card) card.remove();
                                } else {
                                    showToast(res.error || "Failed to revoke key", "error");
                                }
                            }
                        },
                    }),
                ],
            }),
        ],
    });
}

// ---------------------------------------------------------------------------
// Create Key Modal
// ---------------------------------------------------------------------------

let createKeyModal = null;

function openCreateKeyModal() {
    if (createKeyModal) {
        createKeyModal.style.display = "flex";
        return;
    }
    const modal = el("div", {
        id: "create-key-modal",
        style: {
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0,0,0,0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: "1000",
        },
        children: [
            el("div", {
                style: {
                    background: "#fff",
                    borderRadius: "20px",
                    padding: "24px",
                    maxWidth: "420px",
                    width: "90%",
                    maxHeight: "90vh",
                    overflowY: "auto",
                },
                children: [
                    el("h3", { style: { margin: "0 0 16px", fontSize: "1.25rem", fontWeight: "800" }, textContent: "Create API Key" }),
                    el("label", { style: { display: "block", fontSize: "0.9rem", fontWeight: "600", marginBottom: "8px" }, textContent: "Tier" }),
                    el("select", {
                        id: "create-key-tier",
                        style: {
                            width: "100%",
                            padding: "12px",
                            border: "1px solid #eaeaea",
                            borderRadius: "12px",
                            fontSize: "1rem",
                            marginBottom: "16px",
                        },
                        children: [
                            el("option", { value: "free", textContent: "Free" }),
                            el("option", { value: "pro", textContent: "Pro" }),
                        ],
                    }),
                    el("label", { style: { display: "block", fontSize: "0.9rem", fontWeight: "600", marginBottom: "8px" }, textContent: "Label (optional)" }),
                    el("input", {
                        id: "create-key-label",
                        type: "text",
                        placeholder: "My API Key",
                        style: {
                            width: "100%",
                            padding: "12px",
                            border: "1px solid #eaeaea",
                            borderRadius: "12px",
                            fontSize: "1rem",
                            marginBottom: "20px",
                        },
                    }),
                    el("div", {
                        style: {
                            display: "flex",
                            gap: "12px",
                        },
                        children: [
                            el("button", {
                                style: {
                                    background: "#666",
                                    color: "#fff",
                                    border: "none",
                                    padding: "12px 24px",
                                    borderRadius: "12px",
                                    fontWeight: "700",
                                    cursor: "pointer",
                                    flex: 1,
                                },
                                textContent: "Cancel",
                                onClick: () => { modal.style.display = "none"; },
                            }),
                            el("button", {
                                id: "create-key-submit",
                                style: {
                                    background: "linear-gradient(135deg, #0088cc, #005588)",
                                    color: "#fff",
                                    border: "none",
                                    padding: "12px 24px",
                                    borderRadius: "12px",
                                    fontWeight: "700",
                                    cursor: "pointer",
                                    flex: 1,
                                },
                                textContent: "Create Key",
                                onClick: async () => {
                                    const tier = document.getElementById("create-key-tier").value;
                                    const label = document.getElementById("create-key-label").value || undefined;
                                    const btn = document.getElementById("create-key-submit");
                                    btn.textContent = "Creating...";
                                    btn.disabled = true;
                                    try {
                                        const res = await api.createKey({ tier, label, scopes: ["read", "search", "download"] });
                                        if (res.ok) {
                                            showToast("API key created successfully", "success");
                                            modal.style.display = "none";
                                            nav("dashboard");
                                        } else {
                                            showToast(res.error || "Failed to create key", "error");
                                            btn.textContent = "Create Key";
                                            btn.disabled = false;
                                        }
                                    } catch (e) {
                                        showToast(e.message || "Error creating key", "error");
                                        btn.textContent = "Create Key";
                                        btn.disabled = false;
                                    }
                                },
                            }),
                        ],
                    }),
                ],
            }),
        ],
    });
    createKeyModal = modal;
    document.body.appendChild(modal);
}

function renderKeyResultModal() {
    return el("div", {
        id: "key-result-modal",
        style: {
            display: "none",
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0,0,0,0.5)",
            alignItems: "center",
            justifyContent: "center",
            zIndex: "1001",
        },
        children: [
            el("div", {
                style: {
                    background: "#fff",
                    borderRadius: "20px",
                    padding: "24px",
                    maxWidth: "420px",
                    width: "90%",
                },
                children: [
                    el("h3", { style: { margin: "0 0 16px", fontSize: "1.25rem", fontWeight: "800" }, textContent: "API Key Created" }),
                    el("div", {
                        style: {
                            background: "#f8f9fa",
                            border: "1px solid #eaeaea",
                            borderRadius: "12px",
                            padding: "16px",
                            marginBottom: "20px",
                            wordBreak: "break-all",
                        },
                        id: "key-result-value",
                        textContent: "",
                    }),
                    el("button", {
                        style: {
                            background: "linear-gradient(135deg, #0088cc, #005588)",
                            color: "#fff",
                            border: "none",
                            padding: "12px 24px",
                            borderRadius: "12px",
                            fontWeight: "700",
                            cursor: "pointer",
                            width: "100%",
                        },
                        textContent: "Copy & Done",
                        onClick: () => {
                            const val = document.getElementById("key-result-value").textContent;
                            navigator.clipboard.writeText(val);
                            document.getElementById("key-result-modal").style.display = "none";
                            showToast("Key copied to clipboard", "success");
                        },
                    }),
                ],
            }),
        ],
    });
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

async function renderSearch(container) {
    clear(container);
    container.appendChild(renderPageHeader("Search", "Search music & media across sources"));

    const searchBox = el("div", {
        style: {
            display: "flex",
            gap: "12px",
            marginBottom: "24px",
        },
        children: [
            el("input", {
                id: "search-input",
                type: "text",
                placeholder: "Search for music, artists, albums...",
                style: {
                    flex: 1,
                    padding: "14px 18px",
                    border: "1px solid #eaeaea",
                    borderRadius: "12px",
                    fontSize: "1rem",
                },
            }),
            el("button", {
                id: "search-btn",
                style: {
                    background: "linear-gradient(135deg, #0088cc, #005588)",
                    color: "#fff",
                    border: "none",
                    padding: "14px 24px",
                    borderRadius: "12px",
                    fontWeight: "700",
                    cursor: "pointer",
                },
                textContent: "Search",
            }),
        ],
    });

    const resultsContainer = el("div", {
        id: "search-results",
        style: {
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
            gap: "16px",
        },
    });

    container.appendChild(searchBox);
    container.appendChild(resultsContainer);

    const input = document.getElementById("search-input");
    const btn = document.getElementById("search-btn");

    const doSearch = async () => {
        const q = input.value.trim();
        if (!q) return;
        clear(resultsContainer);
        resultsContainer.appendChild(renderLoading(resultsContainer));
        try {
            const res = await api.searchMusic(q, "youtube", 10);
            clear(resultsContainer);
            if (!res.ok || !res.data || !res.data.results || res.data.results.length === 0) {
                resultsContainer.appendChild(renderEmptyState("🔍", "No results found", "Try a different query"));
                return;
            }
            res.data.results.forEach((r) => {
                resultsContainer.appendChild(renderSearchResult(r));
            });
        } catch (e) {
            clear(resultsContainer);
            resultsContainer.appendChild(renderEmptyState("⚠️", "Search failed", e.message || "Unknown error"));
        }
    };

    btn.onClick = doSearch;
    input.addEventListener("keypress", (e) => { if (e.key === "Enter") doSearch(); });
}

// ---------------------------------------------------------------------------
// Search Result Card
// ---------------------------------------------------------------------------

function renderSearchResult(r) {
    return el("div", {
        style: {
            background: "#fff",
            border: "1px solid #eaeaea",
            borderRadius: "16px",
            padding: "16px",
            display: "flex",
            flexDirection: "column",
        },
        children: [
            el("div", { style: { fontWeight: "800", fontSize: "0.95rem", marginBottom: "8px", lineHeight: "1.3" }, textContent: r.title || "Unknown" }),
            el("div", { style: { color: "#666", fontSize: "0.85rem", marginBottom: "12px" }, textContent: r.uploader || "Unknown" }),
            el("div", {
                style: {
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginTop: "auto",
                },
                children: [
                    el("span", { style: { fontSize: "0.85rem", color: "#666" }, textContent: r.duration ? formatDuration(r.duration) : "" }),
                    el("button", {
                        style: {
                            background: "linear-gradient(135deg, #0088cc, #005588)",
                            color: "#fff",
                            border: "none",
                            padding: "8px 16px",
                            borderRadius: "10px",
                            fontSize: "0.85rem",
                            fontWeight: "700",
                            cursor: "pointer",
                        },
                        textContent: "Download",
                        onClick: async () => {
                            const res = await api.createAdvancedDownload({
                                url: r.url || r.link || "",
                                source: "youtube",
                            });
                            if (res.ok) {
                                showToast("Download started", "success");
                                nav("downloads");
                            } else {
                                showToast(res.error || "Download failed", "error");
                            }
                        },
                    }),
                ],
            }),
        ],
    });
}

// ---------------------------------------------------------------------------
// Downloads
// ---------------------------------------------------------------------------

async function renderDownloads(container) {
    clear(container);
    container.appendChild(renderPageHeader("Downloads", "Manage your downloads"));

    const downloadsList = el("div", {
        id: "downloads-list",
        style: {
            display: "flex",
            flexDirection: "column",
            gap: "12px",
        },
    });

    container.appendChild(downloadsList);

    try {
        const res = await api.listAdvancedDownloads();
        const jobs = res.ok ? res.data : [];
        if (jobs.length === 0) {
            downloadsList.appendChild(renderEmptyState("⬇️", "No downloads yet", "Add a URL above to start downloading", {
                text: "Start Download",
                onClick: () => nav("search"),
            }));
        } else {
            jobs.forEach((d) => {
                downloadsList.appendChild(renderDownloadCard(d));
            });
        }
    } catch (e) {
        downloadsList.appendChild(renderEmptyState("⚠️", "Failed to load downloads", e.message || "Unknown error"));
    }
}

// ---------------------------------------------------------------------------
// Download Card
// ---------------------------------------------------------------------------

function renderDownloadCard(job) {
    const status = job.status || "unknown";
    const progress = job.progress || 0;
    return el("div", {
        id: `dl-card-${job.job_id}`,
        style: {
            background: "#fff",
            border: "1px solid #eaeaea",
            borderRadius: "16px",
            padding: "16px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
        },
        children: [
            el("div", {
                children: [
                    el("div", { style: { fontWeight: "800", fontSize: "0.95rem", marginBottom: "4px" }, textContent: job.title || "Download" }),
                    el("div", { style: { color: "#666", fontSize: "0.85rem" }, textContent: job.url || job.source || "" }),
                ],
            }),
            el("div", {
                style: {
                    display: "flex",
                    flexDirection: "column",
                    gap: "8px",
                },
                children: [
                    el("div", {
                        style: {
                            display: "flex",
                            alignItems: "center",
                            gap: "12px",
                        },
                        children: [
                            statusBadge(status),
                            progressBar(progress),
                        ],
                    }),
                    el("div", {
                        style: {
                            display: "flex",
                            gap: "8px",
                        },
                        children: [
                            status === "downloading" ? el("button", {
                                style: {
                                    background: "#fff",
                                    border: "1px solid #d63031",
                                    color: "#d63031",
                                    borderRadius: "10px",
                                    padding: "8px 12px",
                                    fontSize: "0.85rem",
                                    cursor: "pointer",
                                },
                                textContent: "Cancel",
                                onClick: async () => {
                                    const res = await api.cancelDownload(job.job_id);
                                    if (res.ok) {
                                        showToast("Download cancelled", "success");
                                        nav("downloads");
                                    } else {
                                        showToast(res.error || "Failed to cancel", "error");
                                    }
                                },
                            }) : null,
                            status === "failed" ? el("button", {
                                style: {
                                    background: "#f8f9fa",
                                    border: "1px solid #eaeaea",
                                    borderRadius: "10px",
                                    padding: "8px 12px",
                                    fontSize: "0.85rem",
                                    cursor: "pointer",
                                },
                                textContent: "Retry",
                                onClick: async () => {
                                    const res = await api.retryDownload(job.job_id);
                                    if (res.ok) {
                                        showToast("Download restarted", "success");
                                        nav("downloads");
                                    } else {
                                        showToast(res.error || "Failed to retry", "error");
                                    }
                                },
                            }) : null,
                        ].filter(Boolean),
                    }),
                ],
            }),
        ],
    });
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

async function renderSettings(container) {
    clear(container);
    container.appendChild(renderPageHeader("Settings", "Configure your preferences"));

    const lang = store.getState().theme || "system";
    const notify = store.getState().isOnline !== false;

    const sections = [
        renderSettingSection("Appearance", [
            renderSettingRow("Theme", () => {
                const themes = ["system", "light", "dark"];
                const current = store.getState().theme;
                const next = themes[(themes.indexOf(current) + 1) % themes.length];
                localStorage.setItem("videl_theme", next);
                applyTheme(next);
                showToast(`Theme: ${next}`, "success");
            }, `Current: ${lang}`),
        ]),
        renderSettingSection("Notifications", [
            renderSettingToggle("Enable notifications", store.getState().isOnline !== false, async (checked) => {
                await api.setNotificationPrefs({ enabled: checked });
                showToast(`Notifications ${checked ? "enabled" : "disabled"}`, "success");
            }),
        ]),
        renderSettingSection("Rate Limit", [
            renderSettingRow("Check Rate Limit", async () => {
                const res = await api.setRateLimit(0, 60);
                if (res.ok) {
                    showToast("Rate limit info loaded", "success");
                } else {
                    showToast(res.error || "Failed", "error");
                }
            }, "View current rate limit status"),
        ]),
    ];

    sections.forEach((s) => container.appendChild(s));
}

function renderSettingSection(title, rows) {
    return el("div", {
        style: {
            background: "#fff",
            border: "1px solid #eaeaea",
            borderRadius: "16px",
            padding: "20px",
            marginBottom: "16px",
        },
        children: [
            el("h3", { style: { margin: "0 0 16px", fontSize: "1.1rem", fontWeight: "800" }, textContent: title }),
            el("div", {
                style: {
                    display: "flex",
                    flexDirection: "column",
                    gap: "12px",
                },
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
            cursor: "pointer",
        },
        children: [
            el("div", {
                children: [
                    el("div", { style: { fontWeight: "700", fontSize: "0.95rem" }, textContent: title }),
                    subtitle && el("div", { style: { color: "#666", fontSize: "0.85rem" }, textContent: subtitle }),
                ].filter(Boolean),
            }),
            el("span", { style: { color: "#0088cc", fontSize: "0.85rem" }, textContent: "›" }),
        ],
        onClick,
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
            el("div", { style: { fontWeight: "700", fontSize: "0.95rem" }, textContent: title }),
            el("label", {
                style: {
                    display: "inline-block",
                    width: "44px",
                    height: "24px",
                    background: checked ? "#0088cc" : "#ccc",
                    borderRadius: "12px",
                    position: "relative",
                    cursor: "pointer",
                },
                children: [
                    el("span", {
                        style: {
                            position: "absolute",
                            top: "2px",
                            left: checked ? "22px" : "2px",
                            width: "20px",
                            height: "20px",
                            background: "#fff",
                            borderRadius: "50%",
                            transition: "left 0.2s",
                        },
                    }),
                ],
                onClick: () => {
                    onChange(!checked);
                },
            }),
        ],
    });
}

// ---------------------------------------------------------------------------
// Navigation state
// ---------------------------------------------------------------------------

let currentUser = null;
let currentView = "auth";
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
        children: [
            el("div", {
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
            }),
            el("div", {
                style: {
                    display: "flex",
                    alignItems: "center",
                    gap: "12px",
                },
                children: [
                    currentUser ? el("span", {
                        style: {
                            fontSize: "0.9rem",
                            color: "#666",
                        },
                        textContent: currentUser.first_name || currentUser.username || "User",
                    }) : null,
                    currentUser ? el("button", {
                        style: {
                            background: "#f8f9fa",
                            border: "1px solid #eaeaea",
                            color: "#d63031",
                            borderRadius: "10px",
                            padding: "6px 14px",
                            fontSize: "0.85rem",
                            cursor: "pointer",
                        },
                        textContent: "Sign out",
                        onClick: () => {
                            api.clearToken();
                            currentUser = null;
                            nav("auth");
                        },
                    }) : null,
                ],
            }),
        ],
    });

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
            } else {
                await renderDashboard(content, currentUser);
            }
            break;
        case "search":
            if (!currentUser) {
                content.appendChild(renderEmptyState("🔐", "Please sign in", "Sign in with Telegram to use search", {
                    text: "Sign in",
                    onClick: () => nav("auth"),
                }));
            } else {
                await renderSearch(content);
            }
            break;
        case "downloads":
            if (!currentUser) {
                content.appendChild(renderEmptyState("🔐", "Please sign in", "Sign in with Telegram to manage downloads", {
                    text: "Sign in",
                    onClick: () => nav("auth"),
                }));
            } else {
                await renderDownloads(content);
            }
            break;
        case "settings":
            if (!currentUser) {
                content.appendChild(renderEmptyState("🔐", "Please sign in", "Sign in with Telegram to access settings", {
                    text: "Sign in",
                    onClick: () => nav("auth"),
                }));
            } else {
                await renderSettings(content);
            }
            break;
        case "admin":
            if (!currentUser || currentUser.tier !== "owner") {
                content.appendChild(renderEmptyState("🔒", "Admin access required", "Owner tier required for admin panel"));
            } else {
                await renderAdmin(content);
            }
            break;
        default:
            content.appendChild(renderEmptyState("❓", "Unknown view", `View "${view}" not found`));
            break;
    }

    // Main button (Telegram native)
    if (tg) {
        tg.MainButton.setText(getMainButtonLabel(view));
        tg.MainButton.show();
        tg.SecondaryButton.hide();
        tg.BackButton.hide();
        // Remove old handler, add new one
        tg.MainButton.off("click");
        tg.MainButton.on("click", () => {
            haptic("light");
            if (view === "auth") {
                nav("dashboard");
            } else if (view === "dashboard") {
                openCreateKeyModal();
            } else if (view === "search") {
                const input = document.getElementById("search-input");
                input?.focus();
            } else if (view === "downloads") {
                const input = document.getElementById("dl-url");
                input?.focus();
            } else if (view === "settings") {
                nav("settings");
            } else if (view === "admin") {
                nav("admin");
            }
        });
    }

    // Toast container
    if (!document.getElementById("toast-container")) {
        const toastContainer = el("div", {
            id: "toast-container",
            style: {
                position: "fixed",
                bottom: "20px",
                left: "50%",
                transform: "translateX(-50%)",
                display: "flex",
                flexDirection: "column",
                gap: "8px",
                zIndex: "2000",
                pointerEvents: "none",
            },
        });
        document.body.appendChild(toastContainer);
    }

    // Key result modal
    if (!document.getElementById("key-result-modal")) {
        document.body.appendChild(renderKeyResultModal());
    }

    // Reload keys listener
    window.removeEventListener("reload-keys", handleReloadKeys);
    window.addEventListener("reload-keys", handleReloadKeys);
}

function handleReloadKeys() {
    if (currentView === "dashboard" && currentUser) {
        const content = document.getElementById("app").children[1];
        renderDashboard(content, currentUser);
    }
}

// ---------------------------------------------------------------------------
// Auth Screen
// ---------------------------------------------------------------------------

function renderAuthScreen(container, onAuth) {
    clear(container);
    const tgUser = window.Telegram?.WebApp?.initDataUnsafe?.user;
    if (tgUser) {
        // Auto-auth in Telegram WebApp
        currentUser = tgUser;
        store.setUser(tgUser);
        nav("dashboard");
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
            el("button", {
                style: {
                    background: "linear-gradient(135deg, #0088cc, #005588)",
                    color: "#fff",
                    border: "none",
                    padding: "14px 24px",
                    borderRadius: "12px",
                    fontSize: "1rem",
                    fontWeight: "700",
                    cursor: "pointer",
                    width: "100%",
                },
                textContent: "🔐 Sign in with Telegram",
                onClick: () => {
                    if (!isTelegramWebApp()) {
                        showToast("Please open this in Telegram WebApp", "info");
                        return;
                    }
                    tg?.sendData("auth");
                },
            }),
            el("p", {
                textContent: "Or open this link in Telegram: /getapi",
                style: { color: "#999", fontSize: "0.9rem", marginTop: "20px" },
            }),
        ],
    }));
}

// ---------------------------------------------------------------------------
// Initialize
// ---------------------------------------------------------------------------

function init() {
    store.loadPersisted();
    applyTheme(store.getState().theme);

    if (isTelegramWebApp()) {
        const user = window.Telegram?.WebApp?.initDataUnsafe?.user;
        if (user) {
            currentUser = user;
            store.setUser(user);
            nav("dashboard");
        } else {
            nav("auth");
        }
        initWebApp();
    } else {
        // Not in Telegram - show auth but still allow usage
        nav("auth");
    }

    window.addEventListener("online", () => {
        store.setOnline(true);
        haptic("success");
    });
    window.addEventListener("offline", () => {
        store.setOnline(false);
        haptic("error");
    });
    window.matchMedia?.("(prefers-color-scheme: dark)").addEventListener("change", () => {
        if (store.getState().theme === "system") {
            applyTheme("system");
        }
    });
}

init();

// Expose for debugging
window.__videl_nav = nav;
window.__videl_currentUser = currentUser;
