// Videl-Api WebApp - Compiled from TypeScript
(function () {
  "use strict";

  // ---- Telegram WebApp wrapper ----
  const tg = window.Telegram?.WebApp || window.tg?.WebApp;
  const isTelegramWebApp = !!tg;

  function getInitData() {
    return (tg && tg.initData) || "";
  }

  function getTelegramUser() {
    return (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) || null;
  }

  function initWebApp() {
    if (tg) {
      tg.ready();
      tg.expand();
      tg.headerColor = "#0088cc";
      tg.backgroundColor = "#ffffff";
      tg.mainButton.setText("Create API Key");
      tg.mainButton.show();
    }
  }

  // ---- DOM helpers ----
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
        e.setAttribute(k, String(v));
      }
    }
    for (const child of children) {
      if (child instanceof HTMLElement) e.appendChild(child);
      else if (typeof child === "string") e.appendChild(document.createTextNode(child));
      else if (child) e.appendChild(document.createTextNode(String(child)));
    }
    return e;
  }

  function clear(node) {
    node.innerHTML = "";
  }

  // ---- Format helpers ----
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

  function tierColor(tier) {
    const colors = { free: "#00b894", pro: "#6c5ce7", owner: "#ffd700" };
    return colors[tier] || "#666";
  }

  function tierBadge(tier) {
    return el(
      "span",
      {
        style: {
          background: tierColor(tier) + "20",
          color: tierColor(tier),
          padding: "4px 10px",
          borderRadius: "12px",
          fontSize: "0.75rem",
          fontWeight: "700",
          textTransform: "uppercase",
          border: `1px solid ${tierColor(tier)}40`,
        },
      },
      [tier.toUpperCase()]
    );
  }

  // ---- API Client ----
  const API_BASE = window.location.origin;
  let apiToken = null;

  const api = {
    setToken(token) {
      apiToken = token;
    },
    async request(endpoint, options = {}) {
      const headers = {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      };
      if (apiToken) headers["X-API-Key"] = apiToken;
      try {
        const res = await fetch(`${API_BASE}${endpoint}`, {
          ...options,
          headers,
        });
        const data = await res.json();
        if (!res.ok) {
          return { ok: false, error: data.error || data.detail || `HTTP ${res.status}` };
        }
        return { ok: true, data };
      } catch (err) {
        return { ok: false, error: err.message || "Network error" };
      }
    },
    async telegramAuth(initData) {
      return this.request("/v1/web/auth/telegram", {
        method: "POST",
        body: JSON.stringify({ init_data: initData }),
      });
    },
    async createKey(body) {
      return this.request("/v1/web/keys/create", {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    async listKeys() {
      return this.request("/v1/web/keys/list");
    },
    async revokeKey(keyId) {
      return this.request(`/v1/web/keys/${keyId}`, { method: "DELETE" });
    },
    async rotateKey(keyId) {
      return this.request(`/v1/web/keys/${keyId}`, {
        method: "PATCH",
        body: JSON.stringify({ action: "rotate" }),
      });
    },
    async getStats() {
      return this.request("/v1/web/stats");
    },
    async getSources() {
      return this.request("/v1/sources");
    },
  };

  // ---- App State ----
  let currentView = "auth";
  let currentUser = null;
  const root = document.getElementById("app");

  // ---- Components ----
  function renderLoading(container, msg = "Loading...") {
    clear(container);
    container.appendChild(
      el(
        "div",
        {
          style: {
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            padding: "60px 20px",
            color: "#666",
          },
        },
        [
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
          el("div", [msg]),
        ]
      )
    );
  }

  function renderError(container, message, onRetry) {
    clear(container);
    const btns = onRetry
      ? [
          el(
            "button",
            {
              className: "btn-primary",
              textContent: "Retry",
              onClick: onRetry,
            },
            []
          ),
        ]
      : [];
    container.appendChild(
      el(
        "div",
        {
          style: {
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            padding: "60px 20px",
            textAlign: "center",
          },
        },
        [
          el("div", { style: { fontSize: "3rem", marginBottom: "16px" } }, ["⚠️"]),
          el("h3", ["Error"]),
          el("p", {
            textContent: message,
            style: { color: "#666", marginBottom: "20px" },
          }),
          ...btns,
        ]
      )
    );
  }

  function renderAuthScreen(container, onAuth) {
    clear(container);
    const user = getTelegramUser();

    if (user) {
      onAuth(user);
      return;
    }

    container.appendChild(
      el(
        "div",
        {
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
        },
        [
          el(
            "div",
            {
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
            },
            ["V"]
          ),
          el("h2", ["Videl-Api"], { style: { marginBottom: "8px" } }),
          el(
            "p",
            {
              textContent:
                "Sign in with Telegram to create and manage your API keys",
              style: { color: "#666", marginBottom: "32px", fontSize: "1.1rem" },
            },
            []
          ),
          el(
            "button",
            {
              className: "btn-primary",
              style: { width: "100%", padding: "16px", fontSize: "1rem", fontWeight: "700" },
              textContent: "🔐 Sign in with Telegram",
              onClick: () => {
                if (!isTelegramWebApp) {
                  alert("Please open this in Telegram WebApp");
                  return;
                }
                tg.sendData("auth");
              },
            },
            []
          ),
          el(
            "p",
            {
              textContent: "Or open this link in Telegram: /getapi",
              style: { color: "#999", fontSize: "0.9rem", marginTop: "20px" },
            },
            []
          ),
        ]
      )
    );
  }

  function renderDashboard(container, user) {
    clear(container);

    // Header
    const header = el(
      "header",
      {
        className: "dashboard-header",
        style: {
          display: "flex",
          alignItems: "center",
          gap: "16px",
          marginBottom: "32px",
          paddingBottom: "24px",
          borderBottom: "1px solid #eaeaea",
        },
      },
      [
        el("img", {
          src: user.photo_url || "https://via.placeholder.com/48",
          alt: "avatar",
          style: { width: "48px", height: "48px", borderRadius: "50%" },
        }),
        el(
          "div",
          [
            el("h1", [`Welcome, ${user.first_name}`], {
              style: { margin: 0, fontSize: "1.5rem", color: "#1a1a2e" },
            }),
            el(
              "p",
              [`${user.username ? "@" + user.username : "Telegram User"}`],
              { style: { margin: 0, color: "#666", fontSize: "0.9rem" } }
            ),
          ],
        ),
      ]
    );

    // Stats grid
    const statsGrid = el("div", {
      className: "stats-grid",
      style: {
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
        gap: "16px",
        marginBottom: "32px",
      },
    });

    const statCards = {
      requests_today: { label: "Requests Today", value: "0", color: "#0088cc" },
      requests_month: { label: "Requests This Month", value: "0", color: "#00b894" },
      bytes_today: { label: "Bandwidth Today", value: "0 B", color: "#6c5ce7" },
      bytes_month: { label: "Bandwidth This Month", value: "0 B", color: "#ffd700" },
    };

    const statEls = {};
    for (const [key, stat] of Object.entries(statCards)) {
      statsGrid.appendChild(
        el(
          "div",
          {
            className: "stat-card",
            style: {
              background: "#fff",
              padding: "20px",
              borderRadius: "16px",
              boxShadow: "0 4px 20px rgba(0,0,0,0.06)",
              border: "1px solid #f0f0f0",
            },
          },
          [
            el("div", [stat.label], {
              style: { fontSize: "0.85rem", color: "#999", marginBottom: "8px" },
            }),
            el(
              "div",
              [stat.value],
              {
                id: `stat-${key}`,
                style: { fontSize: "1.75rem", fontWeight: "800", color: stat.color },
              }
            ),
          ]
        )
      );
      statEls[key] = document.getElementById(`stat-${key}`);
    }

    // Keys section
    const keysList = el("div", {
      id: "keys-list",
      style: {
        display: "flex",
        flexDirection: "column",
        gap: "12px",
        marginBottom: "32px",
      },
    });

    const keysSection = el(
      "div",
      {
        className: "key-section",
        style: { marginBottom: "32px" },
      },
      [
        el("h2", ["Your API Keys"], { style: { marginBottom: "16px", color: "#1a1a2e" } }),
        keysList,
        el(
          "button",
          {
            className: "btn-primary",
            style: {
              width: "100%",
              padding: "16px",
              fontSize: "1rem",
              fontWeight: "700",
              marginTop: "16px",
              background: "linear-gradient(135deg, #0088cc, #005588)",
            },
            textContent: "+ Create New API Key",
            onClick: () => {
              document.getElementById("create-key-modal").style.display = "flex";
            },
          },
          []
        ),
      ]
    );

    // Create key modal
    const createModal = el("div", {
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
      },
      children: [
        el(
          "div",
          {
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
          },
          [
            el("h2", ["Create API Key"], { style: { marginBottom: "20px", color: "#1a1a2e" } }),
            el(
              "div",
              {
                style: { marginBottom: "20px" },
              },
              [
                el("label", ["Tier"], {
                  style: { display: "block", marginBottom: "8px", fontWeight: "600", color: "#1a1a2e" },
                }),
                el(
                  "select",
                  [],
                  {
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
                      el("option", ["Free — 100 req/day"], { value: "free" }),
                      el("option", ["Pro — 1,000 req/day + downloads"], { value: "pro" }),
                      el("option", ["Owner — Unlimited (admin)"], { value: "owner" }),
                    ],
                  }
                ),
                el("label", ["Label (optional)"], {
                  style: { display: "block", marginBottom: "8px", fontWeight: "600", color: "#1a1a2e" },
                }),
                el("input", [], {
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
                el("label", ["Expires In (days, optional)"], {
                  style: { display: "block", marginBottom: "8px", fontWeight: "600", color: "#1a1a2e" },
                }),
                el("input", [], {
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
                el(
                  "button",
                  {
                    id: "create-key-btn",
                    className: "btn-primary",
                    style: { width: "100%", padding: "14px", fontSize: "1rem", fontWeight: "700" },
                    textContent: "Create Key",
                  },
                  []
                ),
                el(
                  "button",
                  {
                    textContent: "Cancel",
                    style: {
                      width: "100%",
                      padding: "12px",
                      marginTop: "10px",
                      background: "#f5f5f5",
                      border: "1px solid #ddd",
                      borderRadius: "10px",
                      color: "#666",
                      fontWeight: "600",
                      cursor: "pointer",
                    },
                    onClick: () => {
                      createModal.style.display = "none";
                    },
                  },
                  []
                ),
              ]
            ),
          ]
        ),
      ],
    });

    // Result modal
    const resultModal = el("div", {
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
      },
      children: [
        el(
          "div",
          {
            className: "modal-content",
            style: {
              background: "#fff",
              borderRadius: "20px",
              padding: "32px",
              maxWidth: "450px",
              width: "90%",
            },
          },
          [
            el("h2", ["🔑 Your API Key"], { style: { marginBottom: "16px", color: "#1a1a2e" } }),
            el(
              "p",
              ["Save this key securely. It won't be shown again."],
              { style: { color: "#666", marginBottom: "20px", fontSize: "0.9rem" } }
            ),
            el(
              "div",
              {
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
              },
              [
                el("input", [], {
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
                el(
                  "button",
                  ["Copy"],
                  {
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
                      if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
                      alert("Copied to clipboard!");
                    },
                  }
                ),
              ]
            ),
            el(
              "button",
              {
                textContent: "Done",
                className: "btn-primary",
                style: { width: "100%", padding: "14px", fontSize: "1rem", fontWeight: "700" },
                onClick: () => {
                  resultModal.style.display = "none";
                  loadKeys();
                },
              },
              []
            ),
          ]
        ),
      ],
    });

    container.appendChild(header);
    container.appendChild(statsGrid);
    container.appendChild(keysSection);
    container.appendChild(createModal);
    container.appendChild(resultModal);

    // Create key handler
    const createBtn = document.getElementById("create-key-btn");
    createBtn.addEventListener("click", async () => {
      const tierSelect = document.getElementById("key-tier");
      const labelInput = document.getElementById("key-label");
      const expiresInput = document.getElementById("key-expires");

      const tier = tierSelect.value;
      const label = labelInput.value || undefined;
      const expires = expiresInput.value ? parseInt(expiresInput.value) : undefined;

      createBtn.disabled = true;
      createBtn.textContent = "Creating...";

      try {
        const res = await api.createKey({ tier, label, expires_in_days: expires });
        if (res.ok && res.data) {
          const input = document.getElementById("key-value-display");
          input.value = res.data.key || "";
          createModal.style.display = "none";
          resultModal.style.display = "flex";
          if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
          loadKeys();
          loadStats();
        } else {
          alert(res.error || "Failed to create key");
        }
      } catch (err) {
        alert(err.message || "Error creating key");
      } finally {
        createBtn.disabled = false;
        createBtn.textContent = "Create Key";
      }
    });

    // Close modals on outside click
    createModal.addEventListener("click", (e) => {
      if (e.target === createModal) createModal.style.display = "none";
    });
    resultModal.addEventListener("click", (e) => {
      if (e.target === resultModal) resultModal.style.display = "none";
    });

    async function loadKeys() {
      clear(keysList);
      try {
        const res = await api.listKeys();
        if (!res.ok || !res.data) {
          keysList.appendChild(
            el("div", { style: { textAlign: "center", color: "#666", padding: "20px" } }, [
              "Unable to load keys",
            ])
          );
          return;
        }
        const keys = res.data.keys || [];
        if (keys.length === 0) {
          keysList.appendChild(
            el(
              "div",
              {
                className: "empty-state",
                style: { textAlign: "center", padding: "40px 20px", color: "#666" },
              },
              [
                el("div", { style: { fontSize: "2rem", marginBottom: "12px" } }, ["🔑"]),
                el("p", ["No API keys yet. Create one below."]),
              ]
            )
          );
          return;
        }
        for (const k of keys) {
          const card = el(
            "div",
            {
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
              },
            },
            [
              el(
                "div",
                [
                  el(
                    "div",
                    [
                      tierBadge(k.tier || "free"),
                      el(
                        "span",
                        [`${k.active ? "● Active" : "○ Inactive"}`],
                        {
                          style: {
                            fontSize: "0.85rem",
                            color: k.active ? "#00b894" : "#d63031",
                            fontWeight: "600",
                          },
                        }
                      ),
                    ],
                    {
                      style: {
                        display: "flex",
                        alignItems: "center",
                        gap: "10px",
                        marginBottom: "6px",
                      },
                    }
                  ),
                  el("div", [k.label || `Key ${k.key_prefix}`], {
                    style: { fontSize: "1rem", fontWeight: "700", color: "#1a1a2e" },
                  }),
                  el("div", [k.key_prefix], {
                    style: {
                      fontSize: "0.85rem",
                      color: "#666",
                      fontFamily: "monospace",
                      marginTop: "4px",
                    },
                  }),
                  el("div", [`Scopes: ${(k.scopes || []).join(", ")}`], {
                    style: { fontSize: "0.8rem", color: "#999", marginTop: "4px" },
                  }),
                ]
              ),
              el(
                "div",
                {
                  style: { display: "flex", gap: "8px", alignItems: "center" },
                },
                [
                  el(
                    "button",
                    ["Revoke"],
                    {
                      style: {
                        padding: "6px 12px",
                        background: "#fee2e2",
                        color: "#d63031",
                        border: "none",
                        borderRadius: "8px",
                        fontWeight: "600",
                        cursor: "pointer",
                      },
                      onClick: async () => {
                        if (confirm("Revoke this API key?")) {
                          await api.revokeKey(k.key_id);
                          loadKeys();
                          loadStats();
                        }
                      },
                    }
                  ),
                  el(
                    "button",
                    ["Rotate"],
                    {
                      style: {
                        padding: "6px 12px",
                        background: "#f3f4f6",
                        color: "#1a1a2e",
                        border: "none",
                        borderRadius: "8px",
                        fontWeight: "600",
                        cursor: "pointer",
                      },
                      onClick: async () => {
                        const res = await api.rotateKey(k.key_id);
                        if (res.ok) {
                          alert(`New key: ${res.data.new_key}`);
                          loadKeys();
                          loadStats();
                        } else {
                          alert(res.error || "Failed to rotate key");
                        }
                      },
                    }
                  ),
                ]
              ),
            ]
          );
          keysList.appendChild(card);
        }
      } catch (err) {
        renderError(keysList, err.message || "Failed to load keys", loadKeys);
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
              } else {
                el.textContent = formatNumber(Number(value));
              }
            }
          }
          const statusEl = document.getElementById("stat-key-status");
          if (statusEl && data.key_status) {
            statusEl.textContent = data.key_status;
            statusEl.style.color = data.key_status === "active" ? "#00b894" : "#d63031";
          }
        }
      } catch (err) {
        console.error("Stats error:", err);
      }
    }

    loadKeys();
    loadStats();
  }

  function renderSources(container) {
    renderLoading(container, "Loading sources...");
    api.getSources().then((res) => {
      clear(container);
      if (!res.ok || !res.data) {
        renderError(container, res.error || "Failed to load sources");
        return;
      }
      const sources = res.data.sources || [];
      container.appendChild(
        el("h2", ["Supported Sources"], { style: { marginBottom: "20px", color: "#1a1a2e" } })
      );
      const grid = el("div", {
        style: {
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
          gap: "16px",
        },
      });
      for (const s of sources) {
        grid.appendChild(
          el(
            "div",
            {
              className: "source-card",
              style: {
                background: "#fff",
                padding: "16px",
                borderRadius: "12px",
                boxShadow: "0 2px 10px rgba(0,0,0,0.05)",
                border: "1px solid #f0f0f0",
              },
            },
            [
              el(
                "div",
                [
                  tierBadge(s.type || "music"),
                  el("span", [
                    s.supports_search ? "🔍 Search" : "📋 URL only",
                  ]),
                ],
                {
                  style: { display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" },
                }
              ),
              el("div", [s.name], {
                style: { fontSize: "1.1rem", fontWeight: "700", color: "#1a1a2e", marginBottom: "6px" },
              }),
              el("div", [s.description], {
                style: { fontSize: "0.85rem", color: "#666", lineHeight: "1.4" },
              }),
            ]
          )
        );
      }
      container.appendChild(grid);
    });
  }

  // ---- Main render ----
  function render() {
    if (currentView === "auth") {
      renderAuthScreen(root, (user) => {
        currentUser = user;
        api.setToken(`vyt_${user.id}`);
        currentView = "dashboard";
        render();
      });
    } else if (currentView === "dashboard") {
      if (!currentUser) {
        currentView = "auth";
        render();
        return;
      }
      renderDashboard(root, currentUser);
    } else if (currentView === "sources") {
      renderSources(root);
    }
    updateMainButton();
  }

  function updateMainButton() {
    if (!tg) return;
    tg.mainButton.offClick();
    if (currentView === "dashboard") {
      tg.mainButton.setText("Create API Key");
      tg.mainButton.show();
      tg.mainButton.onClick(() => {
        document.getElementById("create-key-modal").style.display = "flex";
      });
    } else {
      tg.mainButton.hide();
    }
  }

  // ---- Start ----
  initWebApp();
  render();

  // Expose globally
  window.videlApi = {
    api,
    nav: (view) => {
      currentView = view;
      render();
    },
    currentUser: () => currentUser,
  };
})();
