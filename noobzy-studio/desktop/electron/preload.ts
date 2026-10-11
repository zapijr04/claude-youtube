import { contextBridge } from "electron";

// Secure IPC surface: the renderer never gets direct Node/fs/child_process
// access. Today this only exposes the backend's base URL; future IPC
// (native file dialogs, local-file drag/drop) would be added here as
// narrowly-scoped invoke/handle channels, not a generic "run this" bridge.
contextBridge.exposeInMainWorld("NOOBZY_API_BASE", "http://127.0.0.1:8077");
