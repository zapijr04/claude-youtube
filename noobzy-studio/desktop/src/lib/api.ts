// Thin fetch wrapper over the NOOBZY backend (FastAPI, app/main.py).
// The backend base URL is configurable so the same renderer bundle works
// in `npm run dev` (Vite dev server) and inside the packaged Electron app.

export const API_BASE =
  (window as any).NOOBZY_API_BASE ?? "http://127.0.0.1:8077";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${init?.method ?? "GET"} ${path} failed (${res.status}): ${text}`);
  }
  return res.json() as Promise<T>;
}

export interface Project {
  id: string;
  name: string;
  preset: "LONG_FORM_STORY" | "SHORT_EGG_REVEAL";
  status: string;
  target_duration_sec: number;
  created_at: string;
}

export interface SourceMedia {
  id: string;
  project_id: string;
  path: string;
  codec: string;
  width: number;
  height: number;
  fps: number;
  duration_sec: number;
  has_audio: boolean;
  thumbnails: string[];
  waveform_path: string | null;
}

export interface SkillManifest {
  id: string;
  version: string;
  title: string;
  description: string;
  triggers: string[];
  capabilities: string[];
  enabled: boolean;
  provenance: string;
}

export interface ComputeProviderStatus {
  provider: string;
  [key: string]: unknown;
}

export const api = {
  listProjects: () => request<Project[]>("/projects"),
  createProject: (body: { name: string; preset: Project["preset"]; target_duration_sec: number }) =>
    request<Project>("/projects", { method: "POST", body: JSON.stringify(body) }),
  getProject: (id: string) => request<Project>(`/projects/${id}`),

  importMedia: async (projectId: string, file: File): Promise<SourceMedia> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_BASE}/projects/${projectId}/media`, { method: "POST", body: form });
    if (!res.ok) throw new Error(`import failed: ${res.status}`);
    return res.json();
  },

  analyze: (projectId: string, mediaId: string) =>
    request(`/projects/${projectId}/analyze?media_id=${mediaId}`, { method: "POST" }),

  getTimeline: (projectId: string) => request(`/projects/${projectId}/timeline`),

  render: (projectId: string, mediaId: string, sfxDensity = "balanced") =>
    request(`/projects/${projectId}/render`, {
      method: "POST",
      body: JSON.stringify({ media_id: mediaId, sfx_density: sfxDensity }),
    }),

  listSkills: (enabledOnly = false) => request<SkillManifest[]>(`/skills?enabled_only=${enabledOnly}`),
  approveSkill: (id: string) => request(`/skills/${id}/approve`, { method: "POST" }),

  listMemory: (kind?: string) => request(`/memory${kind ? `?kind=${kind}` : ""}`),
  remember: (kind: string, key: string, value: Record<string, unknown>) =>
    request("/memory", { method: "POST", body: JSON.stringify({ kind, key, value }) }),

  creativeBrief: (text: string, projectId?: string) =>
    request("/creative-brief", { method: "POST", body: JSON.stringify({ text, project_id: projectId }) }),

  computeProviders: () => request<ComputeProviderStatus[]>("/compute/providers"),

  exportOtio: (projectId: string, mediaId: string) =>
    request(`/projects/${projectId}/export/otio?media_id=${mediaId}`),
  exportFcpxml: (projectId: string, mediaId: string) =>
    request(`/projects/${projectId}/export/fcpxml?media_id=${mediaId}`),
  exportSrt: (projectId: string, mode: "selective" | "full") =>
    request(`/projects/${projectId}/export/srt?mode=${mode}`),
  exportTimelineJson: (projectId: string) =>
    request(`/projects/${projectId}/export/timeline.json`),
};
