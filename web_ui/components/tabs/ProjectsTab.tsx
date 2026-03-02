"use client";

import { useState, useEffect, useCallback } from "react";
import { Markdown } from "@/components/Markdown";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Separator } from "@/components/ui/separator";
import { LogStream } from "@/components/LogStream";
import { VideoPlayer } from "@/components/VideoPlayer";
import { PipelineOptions } from "@/components/PipelineOptions";
import { useSSE } from "@/hooks/useSSE";
import { api, Project, ProjectDetail, SceneEntry, ImportableSource, STEP_LABELS } from "@/lib/api";
import {
  Loader2, Play, Square, RefreshCw, Plus, GitFork, Scissors, Download, Film
} from "lucide-react";

const API_BASE = "http://localhost:8080";

function SceneCard({ scene, projectId, onRefresh }: {
  scene: SceneEntry;
  projectId: string;
  onRefresh: () => void;
}) {
  const steps = [1, 2, 3, 4] as const;
  const stepNames = { 1: "Solver", 2: "Script", 3: "SVGs", 4: "Manim" };

  const handleRemove = async () => {
    if (!confirm(`Remove scene ${scene.scene_index}?`)) return;
    await api.removeScene(projectId, scene.scene_index);
    onRefresh();
  };

  return (
    <Card className="border-zinc-700">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="font-mono">#{scene.scene_index}</Badge>
            <Badge variant={scene.source === "native" ? "secondary" : "outline"} className="text-xs">
              {scene.source}
            </Badge>
            <Badge
              variant={scene.has_video ? "default" : "outline"}
              className={`text-xs ${scene.has_video ? "bg-emerald-600" : ""}`}
            >
              {scene.has_video ? "✅ video" : "⬜ pending"}
            </Badge>
          </div>
          <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive h-7 px-2" onClick={handleRemove}>
            Remove
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 pt-0">
        <Markdown className="prose prose-sm prose-invert max-w-none text-muted-foreground leading-relaxed">{scene.query}</Markdown>

        <div className="flex flex-wrap gap-1.5">
          {steps.map((s) => (
            <Badge key={s} variant={scene.checkpoints[s] ? "default" : "outline"} className="text-xs">
              {scene.checkpoints[s] ? "✅" : "⬜"} {stepNames[s]}
            </Badge>
          ))}
        </div>

        {scene.has_video && scene.video_url && (
          <VideoPlayer videoUrl={scene.video_url} />
        )}

        {scene.solver && (
          <Accordion type="single" collapsible>
            <AccordionItem value="solver">
              <AccordionTrigger className="text-xs py-2">Solver Result — {(scene.solver as { topic?: string }).topic ?? "—"}</AccordionTrigger>
              <AccordionContent>
                <ol className="text-xs space-y-2 list-decimal list-inside">
                  {((scene.solver as { steps?: Array<{ step_number: number; concept: string; description: string }> }).steps ?? []).map((st) => (
                    <li key={st.step_number}>
                      <strong>{st.concept}</strong>:{" "}
                      <Markdown className="prose prose-xs prose-invert max-w-none">{st.description}</Markdown>
                    </li>
                  ))}
                </ol>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        )}

        {scene.script && (
          <Accordion type="single" collapsible>
            <AccordionItem value="script">
              <AccordionTrigger className="text-xs py-2">
                Voiceover Script ({((scene.script as { segments?: unknown[] }).segments ?? []).length} segments)
              </AccordionTrigger>
              <AccordionContent>
                <ol className="text-xs space-y-3 list-decimal list-inside">
                  {((scene.script as { segments?: Array<{ id: string; script: string; visual_action: string }> }).segments ?? []).map((seg) => (
                    <li key={seg.id}>
                      <Markdown className="prose prose-xs prose-invert max-w-none">{seg.script}</Markdown>
                      <div className="italic text-muted-foreground ml-4 mt-0.5">
                        ↪ <Markdown className="prose prose-xs prose-invert max-w-none inline-block">{seg.visual_action}</Markdown>
                      </div>
                    </li>
                  ))}
                </ol>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        )}
      </CardContent>
    </Card>
  );
}

export function ProjectsTab() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [projectDetail, setProjectDetail] = useState<ProjectDetail | null>(null);
  const [importSources, setImportSources] = useState<ImportableSource[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(false);

  // New project form
  const [newAudience, setNewAudience] = useState("high school student");
  const [carrySolver, setCarrySolver] = useState(false);

  // Add scene form
  const [sceneQuery, setSceneQuery] = useState("");
  const [sceneIndex, setSceneIndex] = useState("");

  // Import form
  const [importSource, setImportSource] = useState("");

  // Run scene form
  const [runSceneIndex, setRunSceneIndex] = useState("");
  const [runFromStep, setRunFromStep] = useState("1");
  const [runNudges, setRunNudges] = useState({ 1: "", 2: "", 3: "", 4: "" });
  const [runForceFix, setRunForceFix] = useState("");
  const [runForceFixImagePath, setRunForceFixImagePath] = useState<string | null>(null);
  const [runForceFixImagePreview, setRunForceFixImagePreview] = useState<string | null>(null);
  const [runUploadingImage, setRunUploadingImage] = useState(false);
  const [runModelProvider, setRunModelProvider] = useState("google");
  const [runTtsProvider, setRunTtsProvider] = useState("local");
  const [runLanguage, setRunLanguage] = useState("darija");

  const { logs, running, videoUrl, error, start, stop } = useSSE();

  const fetchProjects = useCallback(async () => {
    setLoadingProjects(true);
    const data = await api.getProjects().catch(() => []);
    setProjects(data);
    setLoadingProjects(false);
  }, []);

  const fetchDetail = useCallback(async (id: string) => {
    if (!id) { setProjectDetail(null); return; }
    const data = await api.getProject(id).catch(() => null);
    setProjectDetail(data);
  }, []);

  const fetchImportSources = useCallback(async () => {
    const data = await api.getImportableSources().catch(() => []);
    setImportSources(data);
  }, []);

  useEffect(() => { fetchProjects(); }, [fetchProjects]);
  useEffect(() => { fetchImportSources(); }, [fetchImportSources]);
  useEffect(() => { fetchDetail(selectedProjectId); }, [selectedProjectId, fetchDetail]);

  const refresh = () => {
    fetchProjects();
    if (selectedProjectId) fetchDetail(selectedProjectId);
  };

  const handleNewProject = async () => {
    const res = await api.newProject(newAudience, carrySolver);
    await fetchProjects();
    setSelectedProjectId(res.project_id);
  };

  const handleAddScene = async () => {
    if (!selectedProjectId || !sceneQuery.trim()) return;
    const idx = sceneIndex.trim() ? parseInt(sceneIndex) : undefined;
    await api.addScene(selectedProjectId, sceneQuery, idx);
    setSceneQuery("");
    setSceneIndex("");
    await fetchDetail(selectedProjectId);
  };

  const handleImportScene = async () => {
    if (!selectedProjectId || !importSource) return;
    await api.importScene(selectedProjectId, importSource);
    setImportSource("");
    await fetchDetail(selectedProjectId);
  };

  const handleFork = async () => {
    if (!selectedProjectId) return;
    const res = await api.forkProject(selectedProjectId);
    await fetchProjects();
    setSelectedProjectId(res.project_id);
  };

  const handleRunScene = () => {
    if (!selectedProjectId || !runSceneIndex) return;
    const nudges = Object.fromEntries(
      Object.entries(runNudges).map(([k, v]) => [Number(k), v])
    );
    start(`${API_BASE}/api/projects/${selectedProjectId}/run-scene`, {
      scene_index: parseInt(runSceneIndex),
      from_step: parseInt(runFromStep),
      nudge_1: nudges[1] ?? "",
      nudge_2: nudges[2] ?? "",
      nudge_3: nudges[3] ?? "",
      nudge_4: nudges[4] ?? "",
      force_fix_prompt: runForceFix,
      force_fix_image_path: runForceFixImagePath,
      model_provider: runModelProvider,
      tts_provider: runTtsProvider,
      language: runLanguage,
    });
  };

  const handleRunForceFixImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setRunForceFixImagePreview(URL.createObjectURL(file));
    setRunUploadingImage(true);
    try {
      const path = await api.uploadFile(file);
      setRunForceFixImagePath(path);
    } finally {
      setRunUploadingImage(false);
    }
  };

  const handleStitch = () => {
    if (!selectedProjectId) return;
    start(`${API_BASE}/api/projects/${selectedProjectId}/stitch`, {});
  };

  return (
    <div className="space-y-6">
      {/* Header: project selector + new project */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center justify-between">
              Projects
              <Button size="sm" variant="ghost" onClick={refresh} disabled={loadingProjects} className="gap-1.5">
                <RefreshCw className={`h-3.5 w-3.5 ${loadingProjects ? "animate-spin" : ""}`} />
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Select value={selectedProjectId} onValueChange={setSelectedProjectId}>
              <SelectTrigger>
                <SelectValue placeholder="Select a project…" />
              </SelectTrigger>
              <SelectContent>
                {projects.map((p) => (
                  <SelectItem key={p.project_id} value={p.project_id}>
                    <span className="font-mono text-xs text-muted-foreground">{p.project_id.slice(0, 8)}…</span>
                    {" — "}
                    <span>{p.scene_count} scene(s)</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {selectedProjectId && projectDetail && (
              <div className="text-xs text-muted-foreground space-y-0.5">
                <p>Audience: {projectDetail.audience}</p>
                <p>Carry solver: {projectDetail.carry_solver_context ? "Yes" : "No"}</p>
                <p>{projectDetail.scenes.length} scene(s)</p>
              </div>
            )}
            {selectedProjectId && (
              <Button size="sm" variant="outline" onClick={handleFork} className="gap-1.5">
                <GitFork className="h-3.5 w-3.5" /> Fork Project
              </Button>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">New Project</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Audience</Label>
              <Input
                value={newAudience}
                onChange={(e) => setNewAudience(e.target.value)}
                placeholder="high school student"
              />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="carry"
                checked={carrySolver}
                onCheckedChange={(v) => setCarrySolver(!!v)}
              />
              <Label htmlFor="carry" className="cursor-pointer text-sm">Carry solver context across scenes</Label>
            </div>
            <Button size="sm" onClick={handleNewProject} className="gap-1.5">
              <Plus className="h-3.5 w-3.5" /> Create Project
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Scene management (only shown when project selected) */}
      {selectedProjectId && (
        <>
          {/* Add / Import scenes */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Add Scene</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">Scene Query</Label>
                  <Textarea
                    rows={3}
                    value={sceneQuery}
                    onChange={(e) => setSceneQuery(e.target.value)}
                    placeholder="What should this scene explain?"
                    className="resize-none"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Insert at index (optional, shifts others)</Label>
                  <Input
                    type="number"
                    value={sceneIndex}
                    onChange={(e) => setSceneIndex(e.target.value)}
                    placeholder="leave blank to append"
                  />
                </div>
                <Button size="sm" onClick={handleAddScene} disabled={!sceneQuery.trim()} className="gap-1.5">
                  <Plus className="h-3.5 w-3.5" /> Add Scene
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Import Scene</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">Source</Label>
                  <Select value={importSource} onValueChange={setImportSource}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select run or scene…" />
                    </SelectTrigger>
                    <SelectContent>
                      {importSources.map((s) => (
                        <SelectItem key={`${s.type}:${s.path}`} value={s.path}>
                          <Badge variant="outline" className="text-xs mr-1">{s.type}</Badge>
                          {s.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <Button size="sm" onClick={handleImportScene} disabled={!importSource} className="gap-1.5">
                  <Download className="h-3.5 w-3.5" /> Import
                </Button>
              </CardContent>
            </Card>
          </div>

          {/* Scene list */}
          {projectDetail && projectDetail.scenes.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                Scenes ({projectDetail.scenes.length})
              </h3>
              {projectDetail.scenes.map((scene) => (
                <SceneCard
                  key={scene.scene_index}
                  scene={scene}
                  projectId={selectedProjectId}
                  onRefresh={() => fetchDetail(selectedProjectId)}
                />
              ))}
            </div>
          )}

          <Separator />

          {/* Run scene */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Run Scene</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-4 flex-wrap items-end">
                <div className="space-y-1.5">
                  <Label className="text-xs">Scene Index</Label>
                  <Input
                    type="number"
                    value={runSceneIndex}
                    onChange={(e) => setRunSceneIndex(e.target.value)}
                    placeholder="e.g. 1"
                    className="w-28"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">From Step</Label>
                  <Select value={runFromStep} onValueChange={setRunFromStep}>
                    <SelectTrigger className="w-52">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(STEP_LABELS).map(([num, name]) => (
                        <SelectItem key={num} value={num}>
                          {num} — {name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <Accordion type="single" collapsible>
                <AccordionItem value="nudges">
                  <AccordionTrigger className="text-sm">Per-step nudges (optional)</AccordionTrigger>
                  <AccordionContent>
                    <div className="space-y-3 pt-2">
                      {([1, 2, 3, 4] as const).map((step) => (
                        <div key={step} className="space-y-1.5">
                          <Label className="text-xs">Step {step} — {STEP_LABELS[step]}</Label>
                          <Input
                            placeholder={`Nudge for step ${step}…`}
                            value={runNudges[step]}
                            onChange={(e) => setRunNudges((n) => ({ ...n, [step]: e.target.value }))}
                          />
                        </div>
                      ))}
                    </div>
                  </AccordionContent>
                </AccordionItem>
                <AccordionItem value="fix">
                  <AccordionTrigger className="text-sm">Force-fix prompt (optional)</AccordionTrigger>
                  <AccordionContent>
                    <div className="space-y-3 mt-2">
                      <Textarea
                        rows={3}
                        value={runForceFix}
                        onChange={(e) => setRunForceFix(e.target.value)}
                        className="resize-none"
                        placeholder="Describe what to fix in the Manim scene…"
                      />
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">Screenshot of the issue (optional)</Label>
                        <Input
                          type="file"
                          accept="image/*"
                          onChange={handleRunForceFixImageUpload}
                          disabled={runUploadingImage}
                          className="text-xs cursor-pointer"
                        />
                        {runUploadingImage && <p className="text-xs text-muted-foreground">Uploading…</p>}
                        {runForceFixImagePreview && !runUploadingImage && (
                          <div className="relative">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img src={runForceFixImagePreview} alt="Fix screenshot" className="max-h-48 rounded border border-zinc-700 object-contain" />
                            <button
                              type="button"
                              onClick={() => { setRunForceFixImagePreview(null); setRunForceFixImagePath(null); }}
                              className="absolute top-1 right-1 bg-zinc-800 text-xs px-1.5 py-0.5 rounded hover:bg-zinc-700"
                            >✕</button>
                          </div>
                        )}
                      </div>
                    </div>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>

              <PipelineOptions
                modelProvider={runModelProvider}
                ttsProvider={runTtsProvider}
                language={runLanguage}
                onModelChange={setRunModelProvider}
                onTtsChange={setRunTtsProvider}
                onLanguageChange={setRunLanguage}
              />

              <div className="flex gap-3 flex-wrap">
                <Button onClick={handleRunScene} disabled={running || !runSceneIndex} className="gap-2">
                  {running ? (
                    <><Loader2 className="h-4 w-4 animate-spin" /> Running…</>
                  ) : (
                    <><Play className="h-4 w-4" /> Run Scene</>
                  )}
                </Button>
                {running && (
                  <Button variant="outline" onClick={stop} className="gap-2">
                    <Square className="h-4 w-4" /> Stop
                  </Button>
                )}
                <Button
                  variant="secondary"
                  onClick={handleStitch}
                  disabled={running}
                  className="gap-2 ml-auto"
                >
                  <Film className="h-4 w-4" /> Stitch All Scenes
                </Button>
              </div>
            </CardContent>
          </Card>

          {error && (
            <Card className="border-destructive">
              <CardContent className="pt-4">
                <p className="text-destructive text-sm font-mono">{error}</p>
              </CardContent>
            </Card>
          )}

          <LogStream logs={logs} />
          <VideoPlayer videoUrl={videoUrl} />
        </>
      )}
    </div>
  );
}
