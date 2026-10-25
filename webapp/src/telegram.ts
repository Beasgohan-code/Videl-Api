// Telegram WebApp SDK wrapper - TypeScript
declare global {
  interface Window {
    Telegram?: WebAppTelegram;
    tg?: WebAppTelegram;
  }
}

interface WebAppTelegram {
  WebApp: {
    initData: string;
    initDataUnsafe: {
      user?: {
        id: number;
        first_name: string;
        last_name?: string;
        username?: string;
        photo_url?: string;
      };
    };
    version: string;
    platform: string;
    colorScheme: string;
    themeParams: any;
    isExpanded: boolean;
    viewportHeight: number;
    viewportStableHeight: number;
    headerColor: string;
    backgroundColor: string;
    sendData(data: string): void;
    switchInlineQuery(query: string): void;
    switchInlineQueryChooseChat(query: string): void;
    setHeaderColor(color: string): void;
    setBackgroundColor(color: string): void;
    setBottomBarColor(color: string): void;
    showAlert(message: string): void;
    showConfirm(message: string, callback?: (confirmed: boolean) => void): void;
    showPopup(params: any, callback?: (buttonId: string) => void): void;
    showScanQrPopup(params: any, callback?: (text: string) => void): void;
    showCustomKeyboard(params: any): void;
    closeCustomKeyboard(): void;
    mainButton: {
      text: string;
      color: string;
      textColor: string;
      isVisible: boolean;
      isActive: boolean;
      isProgressVisible: boolean;
      show(): void;
      hide(): void;
      enable(): void;
      disable(): void;
      showProgress(leave?: boolean): void;
      hideProgress(): void;
      onClick(fn: () => void): void;
      offClick(fn: () => void): void;
    };
    HapticFeedback: {
      impactOccurred(style: "light" | "medium" | "heavy" | "rigid" | "soft"): void;
      notificationOccurred(type: "error" | "success" | "warning"): void;
      selectionChanged(): void;
    };
    onEvent(eventType: string, eventHandler: Function): void;
    offEvent(eventType: string, eventHandler: Function): void;
    ready(): void;
    expand(): void;
    close(): void;
    readOnly: boolean;
  };
}

const tg = window.Telegram?.WebApp || window.tg?.WebApp;

export { tg };
export type { WebAppTelegram };

// Helper to get initData
export function getInitData(): string {
  return tg?.initData || "";
}

// Helper to get user
export function getTelegramUser(): any {
  return tg?.initDataUnsafe?.user || null;
}

// Helper to check if running in Telegram
export function isTelegramWebApp(): boolean {
  return !!tg;
}

// Initialize WebApp
export function initWebApp(): void {
  if (tg) {
    tg.ready();
    tg.expand();
    tg.mainButton.setText("Create API Key");
    tg.mainButton.show();
  }
}
