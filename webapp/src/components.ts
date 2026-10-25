// UI Components - TypeScript (no raw HTML templates)
import { tg, isTelegramWebApp, getTelegramUser } from "./telegram";
import { api } from "./api";

// ---- Type definitions ----

export interface User {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
}

export interface KeyData {
  key_id: string;
  key_prefix: string;
  tier: string;
  scopes: string[];
  active: boolean;
  rate_limit?: number;
  daily_requests: number;
  monthly_requests: number;
  daily_bytes: number;
  monthly_bytes: number;
  expires_at?: string;
  created_at: string;
  label?: string;
}

// ---- DOM helpers ----

export function el(tag: string, props: Record<string, any> = {}, children: any[] = []): HTMLElement {
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

export function clear(el: HTMLElement): void {
  el.innerHTML = "";
}

// ---- Format helpers ----

export function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

export function formatNumber(n: number): string {
  return n.toLocaleString();
}

export function tierColor(tier: string): string {
  const colors: Record<string, string> = {
    free: "#00b894",
    pro: "#6c5ce7",
    owner: "#ffd700",
  };
  return colors[tier] || "#666";
}

export function tierBadge(tier: string): HTMLElement {
  return el("span", {
    className: "tier-badge",
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
    textContent: tier.toUpperCase(),
  });
}

// ---- Components ----

export function renderLoading(container: HTMLElement): void {
  clear(container);
  container.appendChild(
    el("div", {
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
    })
  );
}

export function renderError(container: HTMLElement, message: string, onRetry?: () => void): void {
  clear(container);
  const btns: any[] = [];
  if (onRetry) {
    btns.push(
      el("button", {
        className: "btn-primary",
        textContent: "Retry",
        onClick: onRetry,
      })
    );
  }
  container.appendChild(
    el("div", {
      className: "empty-state",
      style: {
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "60px 20px",
        textAlign: "center",
      },
      children: [
        el("div", {
          style: {
            fontSize: "3rem",
            marginBottom: "16px",
          },
          textContent: "⚠️",
        }),
        el("h3", { textContent: "Error" }),
        el("p", { textContent: message, style: { color: "#666", marginBottom: "20px" } }),
        ...btns,
      ],
    })
  );
}

export function renderAuthScreen(container: HTMLElement, onAuth: (user: User) => void): void {
  clear(container);
  const user = getTelegramUser();

  if (user) {
    onAuth(user);
    return;
  }

  container.appendChild(
    el("div", {
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
          className: "btn-primary",
          style: { width: "100%", padding: "16px", fontSize: "1rem", fontWeight: "700" },
          textContent: "🔐 Sign in with Telegram",
          onClick: () => {
            if (!isTelegramWebApp()) {
              alert("Please open this in Telegram WebApp");
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
    })
  );
}

export function renderDashboard(container: HTMLElement, user: User): void {
  clear(container);

  // Header
  const header = el("header", {
    className: "dashboard-header",
    style: {
      display: "flex",
      alignItems: "center",
      gap: "16px",
      marginBottom: "32px",
      paddingBottom: "24px",
      borderBottom: "1px solid #eaeaea",
    },
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
  });

  // Stats cards
  const statsGrid = el("div", {
    className: "stats-grid",
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
      gap: "16px",
      marginBottom: "32px",
    },
  });

  const statCards: Record<string, { label: string; value: string; color: string }> = {
    requests_today: { label: "Requests Today", value: "0", color: "#0088cc" },
    requests_month: { label: "Requests This Month", value: "0", color: "#00b894" },
    bytes_today: { label: "Bandwidth Today", value: "0 B", color: "#6c5ce7" },
    bytes_month: { label: "Bandwidth This Month", value: "0 B", color: "#ffd700" },
  };

  for (const [key, stat] of Object.entries(statCards)) {
    statsGrid.appendChild(
      el("div", {
        className: "stat-card",
        style: {
          background: "#fff",
          padding: "20px",
          borderRadius: "16px",
          boxShadow: "0 4px 20px rgba(0,0,0,0.06)",
          border: "1px solid #f0f0f0",
        },
        children: [
          el("div", {
            textContent: stat.label,
            style: { fontSize: "0.85rem", color: "#999", marginBottom: "8px" },
          }),
          el("div", {
            textContent: stat.value,
            id: `stat-${key}`,
            style: { fontSize: "1.75rem", fontWeight: "800", color: stat.color },
          }),
        ],
      })
    );
  }

  // Key section
  const keySection = el("div", {
    className: "key-section",
    style: { marginBottom: "32px" },
    children: [
      el("h2", {
        textContent: "Your API Keys",
        style: { marginBottom: "16px", color: "#1a1a2e" },
      }),
      el("div", {
        className: "keys-list",
        id: "keys-list",
        style: {
          display: "flex",
          flexDirection: "column",
          gap: "12px",
        },
        children: [
          el("div", {
            className: "empty-state",
            style: {
              textAlign: "center",
              padding: "40px 20px",
              color: "#666",
            },
            children: [
              el("div", {
                textContent: "🔑",
                style: { fontSize: "2rem", marginBottom: "12px" },
              }),
              el("p", { textContent: "No API keys yet. Create one below." }),
            ],
          }),
        ],
      }),
      el("button", {
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
          (document.getElementById("create-key-modal") as HTMLElement).style.display = "flex";
        },
      }),
    ],
  });

  // Create key modal
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
              el("button", {
                id: "create-key-btn",
                className: "btn-primary",
                style: { width: "100%", padding: "14px", fontSize: "1rem", fontWeight: "700" },
                textContent: "Create Key",
              }),
              el("button", {
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
                  modal.style.display = "none";
                },
              }),
            ],
          }),
        ],
      }),
    ],
  });

  // Result modal (shown after key creation)
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
                  const input = document.getElementById("key-value-display") as HTMLInputElement;
                  input.select();
                  document.execCommand("copy");
                  tg?.HapticFeedback?.notificationOccurred?.("success");
                  alert("Copied to clipboard!");
                },
              }),
            ],
          }),
          el("button", {
            textContent: "Done",
            className: "btn-primary",
            style: { width: "100%", padding: "14px", fontSize: "1rem", fontWeight: "700" },
            onClick: () => {
              resultModal.style.display = "none";
              loadKeys();
            },
          }),
        ],
      }),
    ],
  });

  container.appendChild(header);
  container.appendChild(statsGrid);
  container.appendChild(keySection);
  container.appendChild(modal);
  container.appendChild(resultModal);

  // Wire up create key button
  const createBtn = document.getElementById("create-key-btn") as HTMLButtonElement;
  createBtn?.addEventListener("click", async () => {
    const tierSelect = document.getElementById("key-tier") as HTMLSelectElement;
    const labelInput = document.getElementById("key-label") as HTMLInputElement;
    const expiresInput = document.getElementById("key-expires") as HTMLInputElement;

    const tier = tierSelect.value;
    const label = labelInput.value || undefined;
    const expires = expiresInput.value ? parseInt(expiresInput.value) : undefined;

    createBtn.disabled = true;
    createBtn.textContent = "Creating...";

    try {
      const res = await api.createKey({ tier, label, expires_in_days: expires });
      if (res.ok && res.data) {
        const data = res.data as any;
        const input = document.getElementById("key-value-display") as HTMLInputElement;
        input.value = data.key || "";
        modal.style.display = "none";
        resultModal.style.display = "flex";
        tg?.HapticFeedback?.notificationOccurred?.("success");
        loadKeys();
        loadStats();
      } else {
        alert(res.error || "Failed to create key");
      }
    } catch (err: any) {
      alert(err.message || "Error creating key");
    } finally {
      createBtn.disabled = false;
      createBtn.textContent = "Create Key";
    }
  });

  // Close modals on outside click
  modal.addEventListener("click", (e) => {
    if (e.target === modal) modal.style.display = "none";
  });
  resultModal.addEventListener("click", (e) => {
    if (e.target === resultModal) resultModal.style.display = "none";
  });

  async function loadKeys(): Promise<void> {
    const list = document.getElementById("keys-list") as HTMLElement;
    clear(list);

    try {
      const res = await api.listKeys();
      if (!res.ok || !res.data) {
        list.appendChild(
          el("div", {
            style: { textAlign: "center", color: "#666", padding: "20px" },
            textContent: "Unable to load keys",
          })
        );
        return;
      }

      const keys = (res.data as any).keys || [];

      if (keys.length === 0) {
        list.appendChild(
          el("div", {
            className: "empty-state",
            style: { textAlign: "center", padding: "40px 20px", color: "#666" },
            children: [
              el("div", { textContent: "🔑", style: { fontSize: "2rem", marginBottom: "12px" } }),
              el("p", { textContent: "No API keys yet. Create one below." }),
            ],
          })
        );
        return;
      }

      for (const k of keys as KeyData[]) {
        const card = el("div", {
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
          children: [
            el("div", {
              children: [
                el("div", {
                  style: {
                    display: "flex",
                    alignItems: "center",
                    gap: "10px",
                    marginBottom: "6px",
                  },
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
              ],
            }),
            el("div", {
              style: { display: "flex", gap: "8px", alignItems: "center" },
              children: [
                el("button", {
                  textContent: "Revoke",
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
                }),
                el("button", {
                  textContent: "Rotate",
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
                      alert(`New key: ${res.data?.new_key}`);
                      loadKeys();
                      loadStats();
                    } else {
                      alert(res.error || "Failed to rotate key");
                    }
                  },
                }),
              ],
            }),
          ],
        });
        list.appendChild(card);
      }
    } catch (err: any) {
      renderError(list, err.message || "Failed to load keys", loadKeys);
    }
  }

  async function loadStats(): Promise<void> {
    try {
      const res = await api.getStats();
      if (res.ok && res.data) {
        const data = res.data as any;
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
    } catch (err: any) {
      console.error("Stats error:", err);
    }
  }

  loadKeys();
  loadStats();
}

export function renderSources(container: HTMLElement): void {
  clear(container);
  container.appendChild(
    el("div", {
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
    })
  );

  api.getSources().then((res) => {
    clear(container);
    if (!res.ok || !res.data) {
      renderError(container, res.error || "Failed to load sources");
      return;
    }

    const sources = (res.data as any).sources || [];
    container.appendChild(
      el("h2", {
        textContent: "Supported Sources",
        style: { marginBottom: "20px", color: "#1a1a2e" },
      })
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
        el("div", {
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
              style: {
                display: "flex",
                alignItems: "center",
                gap: "8px",
                marginBottom: "8px",
              },
              children: [
                tierBadge(s.type || "music"),
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
        })
      );
    }

    container.appendChild(grid);
  });
}
