const API_BASE = "http://localhost:8080";

export interface Run {
  run_id: string;
  query: string;
  audience: string;
  query_preview: string;
}

export interface RunDetail {
  run_id: string;
  query: string;
  audience: string;
  language: string;
  checkpoints: Record<number, { name: string; done: boolean }>;
  has_scene: boolean;
  has_video: boolean;
  video_url: string | null;
}

export const SUPPORTED_LANGUAGES: { value: string; label: string }[] = [
  { value: "darija", label: "Moroccan Darija" },
  { value: "msa", label: "Modern Standard Arabic" },
  { value: "french", label: "French" },
  { value: "english", label: "English" },
];

export interface Project {
  project_id: string;
  audience: string;
  carry_solver_context: boolean;
  scene_count: number;
}

export interface SceneEntry {
  scene_index: number;
  source: string;
  query: string;
  scene_dir: string;
  has_video: boolean;
  video_url: string | null;
  checkpoints: Record<number, boolean>;
  solver: Record<string, unknown> | null;
  script: Record<string, unknown> | null;
}

export interface ProjectDetail {
  project_id: string;
  audience: string;
  carry_solver_context: boolean;
  scenes: SceneEntry[];
}

export interface ImportableSource {
  type: "run" | "scene";
  path: string;
  label: string;
}

export const api = {
  async getRuns(): Promise<Run[]> {
    const res = await fetch(`${API_BASE}/api/runs`);
    return res.json();
  },

  async getRun(runId: string): Promise<RunDetail> {
    const res = await fetch(`${API_BASE}/api/runs/${runId}`);
    return res.json();
  },

  async getProjects(): Promise<Project[]> {
    const res = await fetch(`${API_BASE}/api/projects`);
    return res.json();
  },

  async getProject(projectId: string): Promise<ProjectDetail> {
    const res = await fetch(`${API_BASE}/api/projects/${projectId}`);
    return res.json();
  },

  async newProject(audience: string, carry_solver_context: boolean): Promise<{ project_id: string }> {
    const res = await fetch(`${API_BASE}/api/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ audience, carry_solver_context }),
    });
    return res.json();
  },

  async addScene(projectId: string, query: string, scene_index?: number): Promise<{ scene_index: number }> {
    const res = await fetch(`${API_BASE}/api/projects/${projectId}/add-scene`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, scene_index: scene_index ?? null }),
    });
    return res.json();
  },

  async importScene(projectId: string, source_path: string): Promise<{ scene_index: number }> {
    const res = await fetch(`${API_BASE}/api/projects/${projectId}/import-scene`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_path }),
    });
    return res.json();
  },

  async removeScene(projectId: string, scene_index: number): Promise<void> {
    await fetch(`${API_BASE}/api/projects/${projectId}/remove-scene`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scene_index }),
    });
  },

  async forkProject(projectId: string): Promise<{ project_id: string }> {
    const res = await fetch(`${API_BASE}/api/projects/${projectId}/fork`, {
      method: "POST",
    });
    return res.json();
  },

  async getImportableSources(): Promise<ImportableSource[]> {
    const res = await fetch(`${API_BASE}/api/importable-sources`);
    return res.json();
  },

  async uploadFile(file: File): Promise<string> {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_BASE}/api/upload`, { method: "POST", body: form });
    const data = await res.json();
    return data.path as string;
  },

  mediaUrl(path: string): string {
    return `${API_BASE}${path}`;
  },
};

export const STEP_LABELS: Record<number, string> = {
  1: "Analytical Solver",
  2: "Script & TTS",
  3: "SVG Assets",
  4: "Manim Code",
  5: "Compile & Fix",
};
