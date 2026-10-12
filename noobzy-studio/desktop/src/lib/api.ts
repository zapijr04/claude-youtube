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

  analyze: (
    projectId: string,
    mediaId: string,
    opts?: { narrationScript?: string; autoStyle?: boolean; applyTargetDuration?: boolean }
  ) =>
    request(
      `/projects/${projectId}/analyze?media_id=${mediaId}` +
        (opts?.applyTargetDuration ? "&apply_target_duration=true" : ""),
      {
        method: "POST",
        body: JSON.stringify({
          narration_script: opts?.narrationScript || null,
          auto_style: opts?.autoStyle ?? true,
        }),
      }
    ),

  getTimeline: (projectId: string) => request(`/projects/${projectId}/timeline`),
  putTimeline: (projectId: string, timeline: unknown) =>
    request(`/projects/${projectId}/timeline`, { method: "PUT", body: JSON.stringify(timeline) }),
  listTimelineVersions: (projectId: string) =>
    request<{ version: number; saved_at: string }[]>(`/projects/${projectId}/timeline/versions`),
  rollbackTimeline: (projectId: string, version: number) =>
    request(`/projects/${projectId}/timeline/rollback?version=${version}`, { method: "POST" }),

  // Point 6: preview is cheap/cached and NEVER writes a file into the
  // project's final-export output location -- only Export Final Video does.
  preview: (projectId: string, mediaId: string, sfxDensity = "balanced") =>
    request(`/projects/${projectId}/preview`, {
      method: "POST",
      body: JSON.stringify({ media_id: mediaId, sfx_density: sfxDensity }),
    }),

  exportFinalVideo: (
    projectId: string,
    mediaId: string,
    opts?: { sfxDensity?: string; outputDir?: string; filename?: string }
  ) =>
    request(`/projects/${projectId}/export/final-video`, {
      method: "POST",
      body: JSON.stringify({
        media_id: mediaId,
        sfx_density: opts?.sfxDensity ?? "balanced",
        output_dir: opts?.outputDir ?? null,
        filename: opts?.filename ?? "final.mp4",
      }),
    }),

  finalExportHistory: (projectId: string) =>
    request<{ id: string; output_path: string; status: string }[]>(
      `/projects/${projectId}/export/final-video/history`
    ),

  voiceCoverageReport: (projectId: string) =>
    request<{
      voice_coverage_ratio: number;
      gaps_over_threshold: { start_sec: number; end_sec: number; duration_sec: number }[];
    }>(`/projects/${projectId}/voice-coverage-report`),

  regenerateNarrationBlock: (projectId: string, blockId: string) =>
    request(`/projects/${projectId}/narration/${blockId}/regenerate`, { method: "POST" }),

  speedRampScene: (projectId: string, sceneId: string, rate: number) =>
    request(`/projects/${projectId}/scenes/${sceneId}/speed-ramp`, {
      method: "POST",
      body: JSON.stringify({ rate }),
    }),

  learnFromReference: async (file: File, skillId: string, title: string) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(
      `${API_BASE}/skills/learn-from-reference?skill_id=${encodeURIComponent(skillId)}&title=${encodeURIComponent(title)}`,
      { method: "POST", body: form }
    );
    if (!res.ok) throw new Error(`learn-from-reference failed: ${res.status}`);
    return res.json();
  },

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
