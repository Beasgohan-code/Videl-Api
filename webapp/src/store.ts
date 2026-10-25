/**
 * State Management - TypeScript
 * Centralized app state with reactivity
 */

type Listener = () => void;

interface AppState {
  user: any | null;
  token: string | null;
  keys: any[];
  stats: any;
  sources: any[];
  searchResults: any[];
  downloads: any[];
  favorites: any[];
  playlists: any[];
  notifications: any[];
  activityFeed: any[];
  theme: "light" | "dark" | "system";
  language: string;
  isOnline: boolean;
  wsConnected: boolean;
  currentView: string;
  modals: Record<string, boolean>;
}

const defaultState: AppState = {
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
  private state: AppState = { ...defaultState };
  private listeners: Set<Listener> = new Set();

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  getState(): AppState {
    return this.state;
  }

  setState(partial: Partial<AppState>): void {
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

  setUser(user: any | null, token: string | null = null): void {
    this.setState({ user, token });
    if (token) localStorage.setItem("videl_token", token);
    else localStorage.removeItem("videl_token");
  }

  setKeys(keys: any[]): void {
    this.setState({ keys });
  }

  setStats(stats: any): void {
    this.setState({ stats });
  }

  setSources(sources: any[]): void {
    this.setState({ sources });
  }

  setDownloads(downloads: any[]): void {
    this.setState({ downloads });
  }

  addDownload(download: any): void {
    this.setState({ downloads: [download, ...this.state.downloads] });
  }

  updateDownload(jobId: string, updates: any): void {
    this.setState({
      downloads: this.state.downloads.map((d) =>
        d.job_id === jobId ? { ...d, ...updates } : d
      ),
    });
  }

  removeDownload(jobId: string): void {
    this.setState({
      downloads: this.state.downloads.filter((d) => d.job_id !== jobId),
    });
  }

  setFavorites(favorites: any[]): void {
    this.setState({ favorites });
  }

  setPlaylists(playlists: any[]): void {
    this.setState({ playlists });
  }

  setNotifications(notifications: any[]): void {
    this.setState({ notifications });
  }

  setActivityFeed(feed: any[]): void {
    this.setState({ activityFeed: feed });
  }

  setCurrentView(view: string): void {
    this.setState({ currentView: view });
  }

  setWsConnected(connected: boolean): void {
    this.setState({ wsConnected: connected });
  }

  setOnline(online: boolean): void {
    this.setState({ isOnline: online });
  }

  openModal(name: string): void {
    this.setState({ modals: { ...this.state.modals, [name]: true } });
  }

  closeModal(name: string): void {
    const modals = { ...this.state.modals };
    delete modals[name];
    this.setState({ modals });
  }

  loadPersisted(): void {
    const token = localStorage.getItem("videl_token");
    if (token) {
      this.state.token = token;
    }
    const theme = localStorage.getItem("videl_theme") as AppState["theme"];
    if (theme) this.state.theme = theme;
    const lang = localStorage.getItem("videl_language");
    if (lang) this.state.language = lang;
  }
}

export const store = new Store();
export type { AppState };
