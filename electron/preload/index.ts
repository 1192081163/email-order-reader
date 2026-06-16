import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("electronAPI", Object.freeze({}));
