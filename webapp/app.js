/**
 * Videl-Api Telegram WebApp
 * Vanilla JavaScript, no build step, no external dependencies
 * Works inside Telegram WebApp and as a regular web page
 */

// ---------------------------------------------------------------------------
// Telegram WebApp SDK
// ---------------------------------------------------------------------------

const tg = window.Telegram?.WebApp || null;

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
    if (!tg) return;
    try {
        tg.ready();
        tg.expand();
        tg.MainButton.setText("Create API Key");
        tg.MainButton.show();
        tg.SecondaryButton.hide();
        tg.BackButton.hide();
        tg.MainButton.off("click");
        tg.MainButton.on("click", () => {
            if (currentView === "dashboard") {
                openCreateKeyModal();
            }
        });
    } catch { }
}

function haptic(type) {
    if (!tg) return;
    try {
        if (type === "success") tg.HapticFeedback.notificationOccurred("success");
        else if (type === "error") tg.HapticFeedback.notificationOccurred("error");
        else if (type === "warning") tg.HapticFeedback.notificationOccurred("warning");
        else tg.HapticFeedback.impactOccurred(type);
    } catch { }
}

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
    haptic(type === "error" ? "error" : "selection");
}

// ---------------------------------------------------------------------------
// API client
// ---------------------------------------------------------------------------

let apiToken = localStorage.getItem("videl_token") || "";

const api = {
    setToken(token) { apiToken = token; },
    get headers() {
        return {
            "Content-Type": "application/json",
            ...(apiToken ? { Authorization: `Bearer ${apiToken}` } : {}),
        };
    },
    async request(path, opts = {}) {
        const res = await fetch(path, {
            ...opts,
            headers: { ...this.headers, ...(opts.headers || {}) },
        });
        let data = null;
        try { data = await res.json(); } catch { data = {}; }
        return { ok: res.ok, status: res.status, data };
    },
    async getStats() { return this.request("/v1/web/stats"); },
    async listKeys() { return this.request("/v1/web/keys/list"); },
    async createKey(payload) { return this.request("/v1/web/keys/create", { method: "POST", body: JSON.stringify(payload) }); },
    async getKey(keyId) { return this.request(`/v1/web/keys/${keyId}`); },
    async revokeKey(keyId) { return this.request(`/v1/web/keys/${keyId}`, { method: "DELETE" }); },
    async rotateKey(keyId) { return this.request(`/v1/web/keys/${keyId}`, { method: "PATCH" }); },
    async ownerKeys() { return this.request("/v1/web/owner/keys"); },
    async telegramAuth(initData) { return this.request("/v1/web/auth/telegram", { method: "POST", body: JSON.stringify({ init_data: initData }) }); },
};

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let currentUser = null;
let currentView = "auth";

const appEl = document.getElementById("app");
if (!appEl) {
    throw new Error("App container not found");
}

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
        } else if (k === "children") {
            (v || []).forEach((c) => {
                if (c) e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
            });
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

function esc(text) {
    return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
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
// Navigation
// ---------------------------------------------------------------------------

function nav(view) {
    currentView = view;
    render();
    if (tg) {
        try {
            tg.MainButton.setText(getMainButtonLabel(view));
        } catch { }
    }
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

// ---------------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------------

async function render() {
    clear(appEl);
    applyTheme(localStorage.getItem("videl_theme") || "system");

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
                        style: { fontSize: "0.9rem", color: "#666" },
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
                            apiToken = "";
                            localStorage.removeItem("videl_token");
                            api.setToken(null);
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

    appEl.appendChild(navBar);
    appEl.appendChild(content);

    // Render view
    switch (currentView) {
        case "auth":
            renderAuthScreen(content);
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
            if (!currentUser) {
                content.appendChild(renderEmptyState("🔐", "Please sign in", "Owner access required", {
                    text: "Sign in",
                    onClick: () => nav("auth"),
                }));
            } else {
                await renderAdmin(content);
            }
            break;
    }
}

// ---------------------------------------------------------------------------
// UI components
// ---------------------------------------------------------------------------

function renderEmptyState(icon, title, subtitle, action) {
    return el("div", {
        style: {
            maxWidth: "420px",
            margin: "60px auto",
            padding: "40px",
            textAlign: "center",
        },
        children: [
            el("div", {
                style: {
                    fontSize: "48px",
                    marginBottom: "20px",
                },
                textContent: icon,
            }),
            el("h2", { style: { marginBottom: "8px" }, textContent: title }),
            el("p", { style: { color: "#666", marginBottom: "24px" }, textContent: subtitle }),
            action ? el("button", {
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
            }) : null,
        ],
    });
}

function renderPageHeader(title, subtitle) {
    return el("div", {
        style: { marginBottom: "20px" },
        children: [
            el("h2", { style: { margin: 0, fontSize: "1.3rem", fontWeight: "800" }, textContent: title }),
            subtitle ? el("p", { style: { margin: "4px 0 0", color: "#666", fontSize: "0.95rem" }, textContent: subtitle }) : null,
        ],
    });
}

function renderCard(children, style) {
    return el("div", {
        style: {
            background: "#fff",
            borderRadius: "16px",
            padding: "20px",
            boxShadow: "0 4px 20px rgba(0,0,0,0.06)",
            ...(style || {}),
        },
        children,
    });
}

function renderStatCard(label, value, color, icon) {
    return el("div", {
        style: {
            background: "#fff",
            borderRadius: "16px",
            padding: "16px",
            boxShadow: "0 4px 20px rgba(0,0,0,0.06)",
            textAlign: "center",
        },
        children: [
            el("div", { style: { fontSize: "2rem", marginBottom: "8px" }, textContent: icon }),
            el("div", { style: { fontSize: "1.5rem", fontWeight: "800", color: color }, textContent: value }),
            el("div", { style: { fontSize: "0.85rem", color: "#666", marginTop: "4px" }, textContent: label }),
        ],
    });
}

function renderButton(text, onClick, style = {}) {
    return el("button", {
        style: {
            background: "linear-gradient(135deg, #0088cc, #005588)",
            color: "#fff",
            border: "none",
            padding: "12px 20px",
            borderRadius: "12px",
            fontSize: "0.95rem",
            fontWeight: "700",
            cursor: "pointer",
            width: "100%",
            ...style,
        },
        textContent: text,
        onClick,
    });
}

// ---------------------------------------------------------------------------
// Auth screen
// ---------------------------------------------------------------------------

function renderAuthScreen(container) {
    clear(container);
    const tgUser = getTelegramUser();
    if (tgUser && isTelegramWebApp()) {
        currentUser = tgUser;
        nav("dashboard");
        return;
    }

    container.appendChild(el("div", {
        className: "auth-card",
        style: {
            maxWidth: "420px",
            margin: "60px auto",
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
            el("h2", { style: { marginBottom: "8px" }, textContent: "Videl-Api" }),
            el("p", { style: { color: "#666", marginBottom: "32px", fontSize: "1.1rem" }, textContent: "Sign in with Telegram to create and manage your API keys" }),
            isTelegramWebApp() ? el("button", {
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
                    tg?.sendData("auth");
                },
            }) : el("p", { style: { color: "#999", fontSize: "0.9rem" }, textContent: "Please open this in Telegram" }),
            el("p", { style: { color: "#999", fontSize: "0.9rem", marginTop: "20px" }, textContent: "Or open this link in Telegram: /getapi" }),
        ],
    }));
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

async function renderDashboard(container, user) {
    clear(container);
    container.appendChild(renderPageHeader("Dashboard", `Welcome back, ${esc(user.first_name || user.username || "User")}`));

    // Stats row
    const statsRow = el("div", {
        style: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "16px", marginBottom: "24px" },
    });

    try {
        const statsRes = await api.getStats();
        const keysRes = await api.listKeys();
        const stats = statsRes.ok ? statsRes.data : {};
        const keys = keysRes.ok ? keysRes.data : [];
        const tierColorMap = { free: "#666", pro: "#0088cc", owner: "#d63031" };
        const userTier = user.tier || "free";
        statsRow.appendChild(renderStatCard("Tier", String(userTier).charAt(0).toUpperCase() + String(userTier).slice(1), tierColorMap[userTier] || "#666", user.tier === "owner" ? "👑" : user.tier === "pro" ? "💎" : "🆓"));
        statsRow.appendChild(renderStatCard("API Keys", keys.length || 0, "#0088cc", "🔑"));
        statsRow.appendChild(renderStatCard("Requests Today", stats.requests_today || 0, "#00b894", "🔍"));
        statsRow.appendChild(renderStatCard("Downloads", stats.downloads_today || 0, "#fdcb6e", "⬇️"));
    } catch {
        statsRow.appendChild(renderStatCard("Tier", "Free", "#666", "🆓"));
        statsRow.appendChild(renderStatCard("API Keys", "0", "#0088cc", "🔑"));
        statsRow.appendChild(renderStatCard("Requests Today", "0", "#00b894", "🔍"));
        statsRow.appendChild(renderStatCard("Downloads", "0", "#fdcb6e", "⬇️"));
    }
    container.appendChild(statsRow);

    // Quick actions
    const actionsRow = el("div", {
        style: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "16px", marginBottom: "24px" },
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

    // Recent keys
    const keysSection = el("div", {
        style: { marginTop: "32px" },
        children: [
            el("div", {
                style: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" },
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
            el("div", { id: "keys-list", style: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: "12px" } }),
        ],
    });
    container.appendChild(keysSection);

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
            keysList.innerHTML = "";
            keyList.slice(0, 5).forEach((k) => {
                keysList.appendChild(renderKeyCard(k));
            });
        }
    } catch {
        keysList.appendChild(renderEmptyState("⚠️", "Failed to load keys", "Unable to load your API keys"));
    }
}

// ---------------------------------------------------------------------------
// Key card
// ---------------------------------------------------------------------------

function renderKeyCard(k) {
    const tier = k.tier || "free";
    const active = k.active !== false;
    return el("div", {
        style: {
            background: "#fff",
            border: `1px solid ${active ? "#eaeaea" : "#d6303130"}`,
            borderRadius: "12px",
            padding: "16px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
        },
        children: [
            el("div", {
                style: { flex: 1 },
                children: [
                    el("div", { style: { fontSize: "0.85rem", color: "#999", marginBottom: "4px" }, textContent: "API Key" }),
                    el("div", { style: { fontFamily: "monospace", fontSize: "0.9rem", wordBreak: "break-all", color: "#1a1a2e" }, textContent: String(k.key || k.key_id || "").slice(0, 20) + "..." }),
                    el("div", { style: { fontSize: "0.8rem", color: "#666", marginTop: "6px" }, textContent: `Tier: ${esc(tier)}` }),
                ],
            }),
            el("div", {
                style: { display: "flex", gap: "8px" },
                children: [
                    el("button", {
                        style: { background: "#f8f9fa", border: "1px solid #eaeaea", color: "#d63031", borderRadius: "8px", padding: "6px 12px", fontSize: "0.85rem", cursor: "pointer" },
                        textContent: "Revoke",
                        onClick: () => { api.revokeKey(k.key_id || k.key).then(() => { showToast("Key revoked", "success"); render(); }); },
                    }),
                    el("button", {
                        style: { background: "#f8f9fa", border: "1px solid #eaeaea", color: "#0088cc", borderRadius: "8px", padding: "6px 12px", fontSize: "0.85rem", cursor: "pointer" },
                        textContent: "Rotate",
                        onClick: () => { api.rotateKey(k.key_id || k.key).then(() => { showToast("Key rotated", "success"); render(); }); },
                    }),
                ],
            }),
        ],
    });
}

// ---------------------------------------------------------------------------
// Create key modal
// ---------------------------------------------------------------------------

function openCreateKeyModal() {
    const modal = el("div", {
        style: {
            position: "fixed",
            top: 0, left: 0, right: 0, bottom: 0,
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
                    borderRadius: "16px",
                    padding: "24px",
                    width: "320px",
                    boxShadow: "0 20px 60px rgba(0,0,0,0.2)",
                },
                children: [
                    el("h3", { style: { margin: "0 0 16px", fontSize: "1.1rem", fontWeight: "800" }, textContent: "Create API Key" }),
                    el("div", {
                        style: { marginBottom: "16px" },
                        children: [
                            el("label", { style: { display: "block", fontSize: "0.9rem", color: "#666", marginBottom: "6px" }, textContent: "Tier" }),
                            el("select", {
                                id: "create-key-tier",
                                style: { width: "100%", padding: "8px", border: "1px solid #eaeaea", borderRadius: "8px", fontSize: "0.9rem" },
                                children: [
                                    el("option", { value: "free", textContent: "Free" }),
                                    el("option", { value: "pro", textContent: "Pro" }),
                                    el("option", { value: "owner", textContent: "Owner" }),
                                ],
                            }),
                        ],
                    }),
                    el("div", {
                        style: { marginBottom: "20px" },
                        children: [
                            el("label", { style: { display: "block", fontSize: "0.9rem", color: "#666", marginBottom: "6px" }, textContent: "Label (optional)" }),
                            el("input", {
                                id: "create-key-label",
                                type: "text",
                                placeholder: "My API Key",
                                style: { width: "100%", padding: "8px", border: "1px solid #eaeaea", borderRadius: "8px", fontSize: "0.9rem" },
                            }),
                        ],
                    }),
                    el("div", {
                        style: { display: "flex", gap: "8px" },
                        children: [
                            el("button", {
                                style: { background: "#f8f9fa", border: "1px solid #eaeaea", color: "#666", borderRadius: "8px", padding: "10px 20px", fontSize: "0.9rem", cursor: "pointer", flex: 1 },
                                textContent: "Cancel",
                                onClick: () => modal.remove(),
                            }),
                            renderButton("Create", async () => {
                                const tier = document.getElementById("create-key-tier").value;
                                const label = document.getElementById("create-key-label").value || undefined;
                                try {
                                    const res = await api.createKey({ tier, label });
                                    if (res.ok) {
                                        showToast("API key created", "success");
                                        modal.remove();
                                        render();
                                    } else {
                                        showToast(res.data.detail || "Failed to create key", "error");
                                    }
                                } catch {
                                    showToast("Failed to create key", "error");
                                }
                            }),
                        ],
                    }),
                ],
            }),
        ],
    });
    document.body.appendChild(modal);
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

async function renderSearch(container) {
    clear(container);
    container.appendChild(renderPageHeader("Search", "Search media across all sources"));

    const resultsDiv = el("div", { id: "search-results", style: { marginTop: "16px" } });

    container.appendChild(el("div", {
        style: { marginBottom: "16px" },
        children: [
            el("input", {
                id: "search-input",
                type: "text",
                placeholder: "Search for music, videos...",
                style: { width: "100%", padding: "12px", border: "1px solid #eaeaea", borderRadius: "12px", fontSize: "1rem" },
            }),
            el("button", {
                style: { marginTop: "10px" },
                textContent: "Search",
                onClick: doSearch,
            }),
            resultsDiv,
        ],
    }));

    const input = document.getElementById("search-input");
    input.addEventListener("keypress", (e) => { if (e.key === "Enter") doSearch(); });
}

async function doSearch() {
    const input = document.getElementById("search-input");
    const resultsDiv = document.getElementById("search-results");
    const query = input.value.trim();
    if (!query) return;
    resultsDiv.innerHTML = "";
    try {
        const res = await api.request(`/v1/search?q=${encodeURIComponent(query)}`);
        const results = res.ok ? res.data : [];
        if (results.length === 0) {
            resultsDiv.appendChild(renderEmptyState("🔍", "No results", "Try a different search query"));
        } else {
            results.forEach((r) => {
                resultsDiv.appendChild(renderSearchResult(r));
            });
        }
    } catch {
        resultsDiv.appendChild(renderEmptyState("⚠️", "Search failed", "Unable to search at this time"));
    }
}

function renderSearchResult(r) {
    return el("div", {
        style: {
            background: "#fff",
            border: "1px solid #eaeaea",
            borderRadius: "12px",
            padding: "12px",
            marginBottom: "10px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
        },
        children: [
            el("div", {
                style: { flex: 1 },
                children: [
                    el("div", { style: { fontWeight: "700", fontSize: "0.95rem" }, textContent: esc(String(r.title || r.name || "Unknown")) }),
                    el("div", { style: { fontSize: "0.85rem", color: "#666" }, textContent: esc(String(r.artist || r.author || "")) }),
                ],
            }),
            el("button", {
                style: { background: "#0088cc", color: "#fff", border: "none", borderRadius: "8px", padding: "8px 16px", fontSize: "0.85rem", cursor: "pointer" },
                textContent: "Download",
                onClick: () => {
                    const url = r.url || r.link || "";
                    if (url) {
                        // Store URL for downloads page or navigate
                        showToast("Use /download in Telegram bot to download", "info");
                    }
                },
            }),
        ],
    });
}

// ---------------------------------------------------------------------------
// Downloads
// ---------------------------------------------------------------------------

async function renderDownloads(container) {
    clear(container);
    container.appendChild(renderPageHeader("Downloads", "Manage your download jobs"));

    try {
        const res = await api.request("/v1/download/queue");
        const jobs = res.ok ? res.data : [];
        if (jobs.length === 0) {
            container.appendChild(renderEmptyState("⬇️", "No downloads", "Start a download from the dashboard or Telegram bot", {
                text: "Create Download",
                onClick: () => {
                    const url = prompt("Enter media URL:");
                    if (url) showToast("Download feature via Telegram bot", "info");
                },
            }));
        } else {
            jobs.forEach((job) => {
                container.appendChild(renderDownloadCard(job));
            });
        }
    } catch {
        container.appendChild(renderEmptyState("⚠️", "Failed to load downloads", "Unable to load download jobs"));
    }
}

function renderDownloadCard(job) {
    return el("div", {
        style: {
            background: "#fff",
            border: "1px solid #eaeaea",
            borderRadius: "12px",
            padding: "16px",
            marginBottom: "12px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
        },
        children: [
            el("div", {
                style: { flex: 1 },
                children: [
                    el("div", { style: { fontWeight: "700", fontSize: "0.95rem" }, textContent: esc(String(job.url || job.title || "Download")) }),
                    el("div", { style: { fontSize: "0.85rem", color: "#666" }, textContent: `Status: ${esc(String(job.status || "unknown"))}` }),
                ],
            }),
            el("span", {
                style: { padding: "4px 10px", borderRadius: "20px", fontSize: "0.8rem", background: "#e3f2fd", color: "#0088cc" },
                textContent: esc(String(job.id || "").slice(0, 8)),
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

    const themeSelect = el("select", {
        style: { width: "100%", padding: "10px", border: "1px solid #eaeaea", borderRadius: "8px", fontSize: "0.9rem", marginBottom: "16px" },
        children: [
            el("option", { value: "system", textContent: "System" }),
            el("option", { value: "light", textContent: "Light" }),
            el("option", { value: "dark", textContent: "Dark" }),
        ],
    });
    themeSelect.value = localStorage.getItem("videl_theme") || "system";
    themeSelect.onchange = (e) => {
        localStorage.setItem("videl_theme", e.target.value);
        applyTheme(e.target.value);
    };

    container.appendChild(el("div", {
        style: { marginBottom: "20px" },
        children: [
            el("label", { style: { display: "block", fontSize: "0.9rem", color: "#666", marginBottom: "6px" }, textContent: "Theme" }),
            themeSelect,
        ],
    }));
    container.appendChild(renderButton("Sign out", () => {
        apiToken = "";
        localStorage.removeItem("videl_token");
        api.setToken(null);
        currentUser = null;
        nav("auth");
    }, { background: "#d63031" }));
}

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------

async function renderAdmin(container) {
    clear(container);
    container.appendChild(renderPageHeader("Admin Panel", "Owner-only management"));

    try {
        const res = await api.ownerKeys();
        const keys = res.ok ? res.data : [];
        if (keys.length === 0) {
            container.appendChild(renderEmptyState("🔑", "No keys", "No API keys in the system"));
        } else {
            keys.forEach((k) => {
                container.appendChild(renderKeyCard(k));
            });
        }
    } catch {
        container.appendChild(renderEmptyState("⚠️", "Failed to load admin data", "Unable to access admin endpoints"));
    }
}

// ---------------------------------------------------------------------------
// Key result modal (for inline display)
// ---------------------------------------------------------------------------

function renderKeyResultModal() {
    const modal = el("div", {
        id: "key-result-modal",
        style: {
            display: "none",
            position: "fixed",
            top: 0, left: 0, right: 0, bottom: 0,
            background: "rgba(0,0,0,0.5)",
            alignItems: "center",
            justifyContent: "center",
            zIndex: "2000",
        },
        children: [
            el("div", {
                style: {
                    background: "#fff",
                    borderRadius: "16px",
                    padding: "24px",
                    width: "320px",
                    boxShadow: "0 20px 60px rgba(0,0,0,0.2)",
                    textAlign: "center",
                },
                children: [
                    el("h3", { style: { margin: "0 0 12px", fontSize: "1.1rem", fontWeight: "800" }, textContent: "API Key" }),
                    el("div", {
                        style: { marginBottom: "16px", fontFamily: "monospace", fontSize: "0.9rem", background: "#f8f9fa", padding: "12px", borderRadius: "8px", wordBreak: "break-all" },
                        id: "key-result-value",
                    }),
                    el("button", {
                        style: { background: "#0088cc", color: "#fff", border: "none", borderRadius: "8px", padding: "10px 24px", fontSize: "0.95rem", cursor: "pointer", width: "100%" },
                        textContent: "Copy & Close",
                        onClick: () => {
                            const val = document.getElementById("key-result-value").textContent;
                            navigator.clipboard?.writeText(val).then(() => showToast("Copied to clipboard", "success"));
                            document.getElementById("key-result-modal").style.display = "none";
                        },
                    }),
                ],
            }),
        ],
    });
    document.body.appendChild(modal);
    return modal;
}

// ---------------------------------------------------------------------------
// Toast container
// ---------------------------------------------------------------------------

function ensureToastContainer() {
    if (!document.getElementById("toast-container")) {
        const container = el("div", { id: "toast-container", style: { position: "fixed", bottom: "20px", left: "50%", transform: "translateX(-50%)", zIndex: "3000", display: "flex", flexDirection: "column", gap: "8px" } });
        document.body.appendChild(container);
    }
}

// ---------------------------------------------------------------------------
// Initialize
// ---------------------------------------------------------------------------

function init() {
    ensureToastContainer();
    applyTheme(localStorage.getItem("videl_theme") || "system");

    if (isTelegramWebApp()) {
        const user = getTelegramUser();
        if (user) {
            currentUser = user;
            nav("dashboard");
        } else {
            nav("auth");
        }
        initWebApp();
    } else {
        nav("auth");
    }

    window.addEventListener("online", () => { showToast("Back online", "success"); });
    window.addEventListener("offline", () => { showToast("You are offline", "warning"); });
    window.matchMedia?.("(prefers-color-scheme: dark)").addEventListener("change", () => {
        if (localStorage.getItem("videl_theme") === "system") {
            applyTheme("system");
        }
    });
}

init();

// Expose for debugging
window.__videl_nav = nav;
window.__videl_currentUser = currentUser;

// Error fallback: show error instead of blank screen
window.addEventListener("error", (e) => {
    const app = document.getElementById("app");
    if (!app) return;
    app.innerHTML = `
        <div style="padding:40px;text-align:center;font-family:sans-serif;">
            <h2 style="color:#d63031;">Videl-Api</h2>
            <p style="color:#666;">Something went wrong loading the app.</p>
            <p style="font-size:0.9rem;color:#999;">${esc(e.message || "Unknown error")}</p>
            <button onclick="location.reload()" style="padding:10px 20px;background:#0088cc;color:#fff;border:none;border-radius:8px;cursor:pointer;">Reload</button>
        </div>
    `;
});
