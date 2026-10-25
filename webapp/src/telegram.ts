/**
 * Telegram WebApp SDK wrapper - TypeScript
 * Provides type-safe access to Telegram WebApp features
 */

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
        language_code?: string;
      };
      query_id?: string;
      auth_date?: number;
      hash?: string;
    };
    version: string;
    platform: string;
    colorScheme: string;
    themeParams: any;
    isExpanded: boolean;
    isClosingConfirmationEnabled: boolean;
    viewportHeight: number;
    viewportStableHeight: number;
    headerColor: string;
    backgroundColor: string;
    bottomBarColor: string;
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
    MainButton: {
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
    SecondaryButton: {
      text: string;
      color: string;
      textColor: string;
      isVisible: boolean;
      isActive: boolean;
      show(): void;
      hide(): void;
      enable(): void;
      disable(): void;
      onClick(fn: () => void): void;
      offClick(fn: () => void): void;
    };
    BackButton: {
      isVisible: boolean;
      show(): void;
      hide(): void;
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

export function getInitData(): string {
  return tg?.initData || "";
}

export function getTelegramUser(): any {
  return tg?.initDataUnsafe?.user || null;
}

export function isTelegramWebApp(): boolean {
  return !!tg;
}

export function getThemeParams(): any {
  return tg?.themeParams || {};
}

export function initWebApp(): void {
  if (tg) {
    tg.ready();
    tg.expand();
    tg.MainButton.setText("Create API Key");
    tg.MainButton.show();
    tg.SecondaryButton.hide();
    tg.BackButton.hide();
  }
}

export function haptic(type: "success" | "error" | "warning" | "selection" | "light" | "medium" | "heavy" | "rigid" | "soft"): void {
  if (!tg) return;
  try {
    if (type === "success") tg.HapticFeedback.notificationOccurred("success");
    else if (type === "error") tg.HapticFeedback.notificationOccurred("error");
    else if (type === "warning") tg.HapticFeedback.notificationOccurred("warning");
    else if (type === "selection") tg.HapticFeedback.selectionChanged();
    else tg.HapticFeedback.impactOccurred(type as any);
  } catch {}
}

export function showAlert(message: string): void {
  tg?.showAlert(message);
}

export function showConfirm(message: string, callback?: (confirmed: boolean) => void): void {
  tg?.showConfirm(message, callback);
}

export function showPopup(params: any, callback?: (buttonId: string) => void): void {
  tg?.showPopup(params, callback);
}
