import type { AppSettings, RendererApi, ScanOrdersRequest, UpdateInfo } from "../shared/types.js";

const { contextBridge, ipcRenderer } = require("electron") as typeof import("electron");

const IPC_CHANNELS = {
  loadSettings: "settings:load",
  saveSettings: "settings:save",
  scanOrders: "orders:scan",
  checkUpdates: "updates:check",
  downloadUpdate: "updates:download",
  installUpdate: "updates:install",
} as const;

const api: RendererApi = {
  loadSettings: () => ipcRenderer.invoke(IPC_CHANNELS.loadSettings),
  saveSettings: (settings: AppSettings) => ipcRenderer.invoke(IPC_CHANNELS.saveSettings, settings),
  scanOrders: (options: ScanOrdersRequest) => ipcRenderer.invoke(IPC_CHANNELS.scanOrders, options),
  checkUpdates: () => ipcRenderer.invoke(IPC_CHANNELS.checkUpdates),
  downloadUpdate: (update: UpdateInfo) => ipcRenderer.invoke(IPC_CHANNELS.downloadUpdate, update),
  installUpdate: (path: string) => ipcRenderer.invoke(IPC_CHANNELS.installUpdate, path),
};

contextBridge.exposeInMainWorld("orderQuickRead", Object.freeze(api));
