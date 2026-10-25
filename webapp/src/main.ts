// Entry Point - TypeScript
import { initWebApp, isTelegramWebApp, tg } from "./telegram";
import { renderAuthScreen, renderDashboard, renderSources, el } from "./components";
import { api } from "./api";

// Initialize Telegram WebApp
initWebApp();

// Set theme colors from Telegram
if (tg) {
  tg.headerColor = "#0088cc";
  tg.backgroundColor = "#ffffff";
}

// Main app container
const root = document.getElementById("app") || el("div", { id: "app" });
if (!document.getElementById("app")) {
  document.body.appendChild(root);
}

let currentView: "auth" | "dashboard" | "sources" = "auth";
let currentUser: any = null;

// Navigation
function nav(view: "auth" | "dashboard" | "sources"): void {
  currentView = view;
  render();
}

function render(): void {
  if (currentView === "auth") {
    renderAuthScreen(root, (user) => {
      currentUser = user;
      api.setToken(`vyt_${user.id}`);
      nav("dashboard");
    });
  } else if (currentView === "dashboard") {
    if (!currentUser) {
      nav("auth");
      return;
    }
    renderDashboard(root, currentUser);
  } else if (currentView === "sources") {
    renderSources(root);
  }
}

// Set main button action based on view
function updateMainButton(): void {
  if (!tg) return;
  tg.mainButton.offClick();
  if (currentView === "dashboard") {
    tg.mainButton.setText("Create API Key");
    tg.mainButton.show();
    tg.mainButton.onClick(() => {
      const modal = document.getElementById("create-key-modal") as HTMLElement;
      if (modal) modal.style.display = "flex";
    });
  } else {
    tg.mainButton.hide();
  }
}

// Override render to update main button
const originalRender = render;
render = () => {
  originalRender();
  updateMainButton();
};

// Back button handling
if (tg) {
  tg.onEvent("themeChanged", () => {
    render();
  });
}

// Start
render();

// Export for global access
(window as any).videlApi = {
  api,
  nav,
  currentUser: () => currentUser,
};
