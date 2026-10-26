/**
 * UI Components - TypeScript
 * Comprehensive component library for Videl-Api WebApp
 */

import { tg, haptic, showAlert, showConfirm, isTelegramWebApp } from "./telegram";
import { api } from "./api";
import { store } from "./store";

// ---- Type definitions ----

export interface User {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
  language_code?: string;
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

export interface DownloadJob {
  job_id: string;
  url: string;
  source?: string;
  user_id: number;
  priority: string;
  status: string;
  progress: number;
  file_path?: string;
  error?: string;
  created_at: string;
  updated_at: string;
  title?: string;
  total_size?: number;
  downloaded_size?: number;
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

export function clear(container: HTMLElement): void {
  container.innerHTML = "";
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

export function formatDuration(seconds?: number): string {
  if (!seconds) return "--";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return h > 0 ? `${h}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}` : `${m}:${s.toString().padStart(2, "0")}`;
}

export function formatDate(iso?: string): string {
  if (!iso) return "--";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
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
      fontSize: "0.7rem",
      fontWeight: "700",
      textTransform: "uppercase",
      border: `1px solid ${tierColor(tier)}40`,
    },
    textContent: tier.toUpperCase(),
  });
}

// ---- Status helpers ----

export function statusBadge(status: string): HTMLElement {
  const colors: Record<string, string> = {
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

export function progressBar(progress: number, fillClass?: string): HTMLElement {
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

export function renderPageHeader(title: string, subtitle?: string): HTMLElement {
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

export function renderCard(children: HTMLElement[], style?: Record<string, string>): HTMLElement {
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

export function btnPrimary(text: string, onClick: () => void, disabled = false): HTMLElement {
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

export function btnSecondary(text: string, onClick: () => void, danger = false): HTMLElement {
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

export function renderStatCard(label: string, value: string, color: string, icon?: string): HTMLElement {
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

export function renderEmptyState(icon: string, title: string, subtitle?: string, action?: { text: string; onClick: () => void }): HTMLElement {
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

// ---- Auth Screen ----

export function renderAuthScreen(container: HTMLElement, onAuth: (user: User) => void): void {
  clear(container);
  const user = (window as any).Telegram?.WebApp?.initDataUnsafe?.user;

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
    })
  );
}

// ---- Dashboard ----

export async function renderDashboard(container: HTMLElement, user: User): Promise<void> {
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

  const statCards: Record<string, { label: string; value: string; color: string; icon: string }> = {
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

  async function loadKeys(): Promise<void> {
    const list = document.getElementById("keys-list") as HTMLElement;
    if (!list) return;
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

      const keys = (res.data as any).keys || [];
      s.setKeys(keys);

      if (keys.length === 0) {
        list.appendChild(renderEmptyState("🔑", "No API keys yet", "Create your first key to access the API", {
          text: "Create Key",
          onClick: () => s.openModal("create-key"),
        }));
        return;
      }

      for (const k of keys as KeyData[]) {
        list.appendChild(renderKeyCard(k));
      }
    } catch (err: any) {
      list.appendChild(renderEmptyState("⚠️", "Failed to load keys", err.message || "Unknown error"));
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
      }
    } catch (err: any) {
      console.error("Stats error:", err);
    }
  }
}

// ---- Key Card ----

export function renderKeyCard(k: KeyData): HTMLElement {
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
            } else {
              showAlert(res.error || "Failed to rotate key");
            }
          }),
        ],
      }),
    ],
  });
}

function showConfirmAsync(message: string): Promise<boolean> {
  return new Promise((resolve) => {
    showConfirm(message, (confirmed) => resolve(confirmed));
  });
}

// ---- Create Key Modal ----

export function renderCreateKeyModal(): HTMLElement {
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
                const tierSelect = document.getElementById("key-tier") as HTMLSelectElement;
                const labelInput = document.getElementById("key-label") as HTMLInputElement;
                const expiresInput = document.getElementById("key-expires") as HTMLInputElement;

                const tier = tierSelect.value;
                const label = labelInput.value || undefined;
                const expires = expiresInput.value ? parseInt(expiresInput.value) : undefined;

                const btn = document.getElementById("create-key-cancel") as HTMLButtonElement;
                btn.disabled = true;
                btn.textContent = "Creating...";

                try {
                  const res = await api.createKey({ tier, label, expires_in_days: expires });
                  if (res.ok && res.data) {
                    const data = res.data as any;
                    const input = document.getElementById("key-value-display") as HTMLInputElement;
                    input.value = data.key || "";
                    modal.style.display = "none";
                    s.closeModal("create-key");
                    s.openModal("key-result");
                    haptic("success");
                  } else {
                    showAlert(res.error || "Failed to create key");
                  }
                } catch (err: any) {
                  showAlert(err.message || "Error creating key");
                } finally {
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

export function renderKeyResultModal(): HTMLElement {
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
                  const input = document.getElementById("key-value-display") as HTMLInputElement;
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

export async function renderSources(container: HTMLElement): Promise<void> {
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

  try {
    const res = await api.getSources();
    clear(container);

    if (!res.ok || !res.data) {
      container.appendChild(renderEmptyState("⚠️", "Failed to load sources", res.error || "Unknown error"));
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
        })
      );
    }

    container.appendChild(grid);
  } catch (err: any) {
    container.appendChild(renderEmptyState("⚠️", "Failed to load sources", err.message || "Unknown error"));
  }
}

// ---- Search Screen ----

export async function renderSearch(container: HTMLElement): Promise<void> {
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

  container.appendChild(
    el("div", {
      style: { maxWidth: "600px", margin: "0 auto" },
      children: [
        el("h2", { textContent: "🔍 Search", style: { marginBottom: "20px", color: "#1a1a2e" } }),
        searchInput,
        sourceSelect,
        btnPrimary("Search", async () => {
          const q = searchInput.value.trim();
          if (!q) return;
          const source = (sourceSelect as HTMLSelectElement).value;
          haptic("light");

          renderLoading(resultsContainer);

          try {
            const res = await api.searchMusic(q, source, 10);
            clear(resultsContainer);
            if (res.ok && res.data) {
              const results = (res.data as any).results || [];
              if (results.length === 0) {
                resultsContainer.appendChild(renderEmptyState("🔍", "No results found", "Try a different query"));
              } else {
                for (const r of results) {
                  resultsContainer.appendChild(renderSearchResult(r));
                }
              }
            } else {
              resultsContainer.appendChild(renderEmptyState("⚠️", "Search failed", res.error || "Unknown error"));
            }
          } catch (err: any) {
            resultsContainer.appendChild(renderEmptyState("⚠️", "Search failed", err.message || "Unknown error"));
          }
        }),
        resultsContainer,
      ],
    })
  );

  // Enter key to search
  searchInput.addEventListener("keypress", (e) => {
    if (e.key === "Enter") {
      (searchInput.parentElement?.querySelector("button") as HTMLButtonElement)?.click();
    }
  });
}

function renderSearchResult(r: any): HTMLElement {
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
          (window as any).videlApi?.nav?.("download") || alert("Download feature coming soon");
        },
      }),
    ],
  });
}

// ---- Download Manager Screen ----

export async function renderDownloads(container: HTMLElement): Promise<void> {
  clear(container);

  container.appendChild(
    el("h2", {
      textContent: "Download Manager",
      style: { marginBottom: "20px", color: "#1a1a2e" },
    })
  );

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

  container.appendChild(
    el("div", {
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
            btnPrimary("Add", async () => {
              const input = document.getElementById("dl-url") as HTMLInputElement;
              const priority = (document.getElementById("dl-priority") as HTMLSelectElement).value;
              const url = input.value.trim();
              if (!url) return;

              try {
                const res = await api.createAdvancedDownload({
                  url,
                  priority: priority as any,
                });
                if (res.ok && res.data) {
                  input.value = "";
                  haptic("success");
                  loadDownloads();
                } else {
                  showAlert(res.error || "Failed to add download");
                }
              } catch (err: any) {
                showAlert(err.message || "Error adding download");
              }
            }),
          ],
        }),
        downloadsList,
      ],
    })
  );

  async function loadDownloads(): Promise<void> {
    try {
      const res = await api.listAdvancedDownloads();
      clear(downloadsList);
      if (res.ok && res.data) {
        const downloads = res.data as any[];
        if (downloads.length === 0) {
          downloadsList.appendChild(renderEmptyState("⬇️", "No downloads yet", "Add a URL above to start downloading"));
        } else {
          for (const d of downloads) {
            downloadsList.appendChild(renderDownloadCard(d));
          }
        }
      } else {
        downloadsList.appendChild(renderEmptyState("⚠️", "Failed to load downloads", res.error || "Unknown error"));
      }
    } catch (err: any) {
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
  const updateWsStatus = (connected: boolean) => {
    if (!wsStatusEl) return;
    const dot = wsStatusEl.querySelector(".ws-dot");
    const text = wsStatusEl.querySelector("span");
    if (connected) {
      wsStatusEl.className = "ws-status connected";
      if (dot) {
        dot.classList.remove("ws-dot");
        dot.classList.add("ws-dot");
      }
      if (text) text.textContent = "Realtime: Connected";
    } else {
      wsStatusEl.className = "ws-status disconnected";
      if (text) text.textContent = "Realtime: Disconnected";
    }
  };

  api.on("ws:open", () => updateWsStatus(true));
  api.on("ws:close", () => updateWsStatus(false));

  // Listen for WebSocket download updates - update individual cards in real-time
  api.on("ws:download_started", (data: any) => {
    haptic("light");
    loadDownloads();
  });
  api.on("ws:download_completed", (data: any) => {
    haptic("success");
    loadDownloads();
  });
  api.on("ws:download_failed", (data: any) => {
    haptic("error");
    loadDownloads();
  });
  api.on("ws:download_progress", (data: any) => {
    // Update individual card progress without full reload
    const { job_id, progress } = data;
    const card = document.querySelector(`[data-job-id="${job_id}"]`);
    if (card) {
      const progressBar = card.querySelector(".progress-bar-fill");
      const progressText = card.querySelector(".progress-text");
      if (progressBar) progressBar.style.width = `${progress}%`;
      if (progressText) progressText.textContent = `${progress}%`;
    }
  });

  // Cleanup WebSocket on page unload
  window.addEventListener("beforeunload", () => {
    api.wsDisconnect();
  });

  return { loadDownloads };
}

function renderDownloadCard(job: DownloadJob): HTMLElement {
  const isDownloading = job.status === "downloading";
  const isPaused = job.status === "paused";
  const isQueued = job.status === "queued";
  const isCompleted = job.status === "completed";
  const isFailed = job.status === "failed";
  const isCancelled = job.status === "cancelled";

  // Determine progress text
  let progressText = `${job.progress}%`;
  if (isQueued) progressText = "Queued";
  else if (isPaused) progressText = "Paused";
  else if (isCompleted) progressText = "Completed";
  else if (isFailed) progressText = `Failed${job.error ? `: ${job.error}` : ""}`;
  else if (isCancelled) progressText = "Cancelled";

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
            } catch (err: any) {
              showAlert(err.message || "Failed to pause");
            }
          }),
          isPaused && btnSecondary("Resume", async () => {
            try {
              await api.resumeDownload(job.job_id);
            } catch (err: any) {
              showAlert(err.message || "Failed to resume");
            }
          }),
          (isQueued || isDownloading || isPaused) && btnSecondary("Cancel", async () => {
            try {
              await api.cancelDownload(job.job_id);
            } catch (err: any) {
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
              });
            } catch (err: any) {
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

export async function renderSettings(container: HTMLElement): Promise<void> {
  clear(container);

  const s = store;

  container.appendChild(
    el("h2", {
      textContent: "Settings",
      style: { marginBottom: "24px", color: "#1a1a2e" },
    })
  );

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
      s.setState({ user: { ...s.getState().user!, notifications: checked } });
      await api.setNotificationPrefs({ download_complete: checked });
    }),
    renderSettingToggle("Payment Received", true, async (checked) => {
      await api.setNotificationPrefs({ payment_received: checked });
    }),
    renderSettingToggle("System Alerts", false, async (checked) => {
      await api.setNotificationPrefs({ system_alerts: checked });
    }),
  ]));

  container.appendChild(
    el("div", {
      style: { maxWidth: "600px", margin: "0 auto" },
      children: [
        el("h2", { textContent: "Settings", style: { marginBottom: "24px", color: "#1a1a2e" } }),
        sections,
      ],
    })
  );
}

function renderSettingSection(title: string, rows: HTMLElement[]): HTMLElement {
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

function renderSettingRow(title: string, onClick: () => void, subtitle: string): HTMLElement {
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

function renderSettingToggle(title: string, checked: boolean, onChange: (checked: boolean) => void): HTMLElement {
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
              onChange((e.target as HTMLInputElement).checked);
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

export function applyTheme(theme: string): void {
  if (theme === "dark" || (theme === "system" && window.matchMedia?.("(prefers-color-scheme: dark)").matches)) {
    document.documentElement.setAttribute("data-theme", "dark");
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
}

// ---- Admin Screen ----

export async function renderAdmin(container: HTMLElement): Promise<void> {
  clear(container);

  container.appendChild(
    el("h2", {
      textContent: "Admin Panel",
      style: { marginBottom: "24px", color: "#1a1a2e" },
    })
  );

  const grid = el("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
      gap: "16px",
      marginBottom: "32px",
    },
  });

  const adminActions: Array<{ title: string; desc: string; onClick: () => void }> = [
    { title: "Users", desc: "Manage all users", onClick: () => { showAlert("User management coming soon"); } },
    { title: "Stats", desc: "Global statistics", onClick: async () => {
      const res = await api.getGlobalStats();
      if (res.ok) {
        const data = res.data as any;
        showAlert(`Total Users: ${data.total_users}\nRequests Today: ${data.total_requests_today}\nDownloads: ${data.total_downloads_today}`);
      }
    } },
    { title: "Webhooks", desc: "Manage webhooks", onClick: () => { showAlert("Webhook management coming soon"); } },
    { title: "Maintenance", desc: "Toggle maintenance mode", onClick: () => { showAlert("Maintenance toggle coming soon"); } },
  ];

  for (const action of adminActions) {
    grid.appendChild(
      el("div", {
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
      })
    );
  }

  container.appendChild(
    el("div", {
      style: { maxWidth: "800px", margin: "0 auto" },
      children: [el("h2", { textContent: "Admin Panel", style: { marginBottom: "24px", color: "#1a1a2e" } }), grid],
    })
  );
}
