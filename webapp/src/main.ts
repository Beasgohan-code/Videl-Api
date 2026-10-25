/**
 * Main Application - TypeScript
 * Videl-Api WebApp entry point with routing and layout
 */

import { tg, initWebApp, haptic, showAlert, isTelegramWebApp } from "./telegram";
import { api } from "./api";
import { store } from "./store";
import {
  el,
  clear,
  btnPrimary,
  btnSecondary,
  renderAuthScreen,
  renderDashboard,
  renderSources,
  renderSearch,
  renderDownloads,
  renderSettings,
  renderAdmin,
  renderEmptyState,
  applyTheme,
  tierBadge,
} from "./components";

// Navigation state
let currentUser: any = null;
let currentView = "auth";

// DOM elements
const app = document.getElementById("app") as HTMLElement;
if (!app) {
  throw new Error("App container not found");
}

function nav(view: string): void {
  currentView = view;
  store.setCurrentView(view);
  render();
}

function getMainButtonLabel(view: string): string {
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

async function render(): Promise<void> {
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
      } else if (view === "dashboard") {
        s.openModal("create-key");
      } else if (view === "search") {
        // Focus search input
        const input = document.getElementById("search-input") as HTMLInputElement;
        input?.focus();
      } else if (view === "downloads") {
        const input = document.getElementById("dl-url") as HTMLInputElement;
        input?.focus();
      } else if (view === "settings") {
        nav("settings");
      } else if (view === "admin") {
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

  // Reload keys listener
  window.removeEventListener("reload-keys", handleReloadKeys);
  window.addEventListener("reload-keys", handleReloadKeys);
}

function handleReloadKeys(): void {
  if (currentView === "dashboard" && currentUser) {
    renderDashboard(document.getElementById("app")!.children[1] as HTMLElement, currentUser);
  }
}

// Initialize
function init(): void {
  store.loadPersisted();
  applyTheme(store.getState().theme);

  // Handle Telegram init data
  if (isTelegramWebApp()) {
    const user = (window as any).Telegram?.WebApp?.initDataUnsafe?.user;
    if (user) {
      currentUser = user;
      store.setUser(user);
      nav("dashboard");
    } else {
      nav("auth");
    }
    initWebApp();
  } else {
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

export { nav, currentUser };
