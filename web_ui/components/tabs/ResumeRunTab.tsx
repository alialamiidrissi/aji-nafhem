"use client";

import { useState, useEffect, useCallback, useRef } from "react";
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
import { api, Run, RunDetail, STEP_LABELS } from "@/lib/api";
import { Loader2, Play, Square, RefreshCw } from "lucide-react";
import { Markdown } from "@/components/Markdown";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8080";

export function ResumeRunTab() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [fromStep, setFromStep] = useState("1");
  const [copyRun, setCopyRun] = useState(false);
  const [nudges, setNudges] = useState<Record<number, string>>({ 1: "", 2: "", 3: "", 4: "", 5: "" });
  const [forceFix, setForceFix] = useState("");
  const [forceFixImagePath, setForceFixImagePath] = useState<string | null>(null);
  const [forceFixImagePreview, setForceFixImagePreview] = useState<string | null>(null);
  const [uploadingImage, setUploadingImage] = useState(false);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const [modelProvider, setModelProvider] = useState("google");
  const [ttsProvider, setTtsProvider] = useState("local");
  const [language, setLanguage] = useState("darija");
  const [loadingRuns, setLoadingRuns] = useState(false);
  const { logs, running, videoUrl, error, start, stop } = useSSE();

  const fetchRuns = useCallback(async () => {
    setLoadingRuns(true);
    const data = await api.getRuns().catch(() => []);
    setRuns(data);
    setLoadingRuns(false);
  }, []);

  useEffect(() => { fetchRuns(); }, [fetchRuns]);

  useEffect(() => {
    if (!selectedRunId) { setRunDetail(null); return; }
    api.getRun(selectedRunId).then((detail) => {
      setRunDetail(detail);
      if (detail.language) setLanguage(detail.language);
    }).catch(() => setRunDetail(null));
  }, [selectedRunId]);

  const handleResume = () => {
    if (!selectedRunId) return;
    start(`${API_BASE}/api/resume`, {
      run_id: selectedRunId,
      from_step: parseInt(fromStep),
      copy_run: copyRun,
      nudge_1: nudges[1],
      nudge_2: nudges[2],
      nudge_3: nudges[3],
      nudge_4: nudges[4],
      nudge_5: nudges[5],
      force_fix_prompt: forceFix,
      force_fix_image_path: forceFixImagePath,
      model_provider: modelProvider,
      tts_provider: ttsProvider,
      language,
    });
  };

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setForceFixImagePreview(URL.createObjectURL(file));
    setUploadingImage(true);
    try {
      const path = await api.uploadFile(file);
      setForceFixImagePath(path);
    } finally {
      setUploadingImage(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Run selector */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center justify-between">
            Select Run
            <Button size="sm" variant="ghost" onClick={fetchRuns} disabled={loadingRuns} className="gap-1.5">
              <RefreshCw className={`h-3.5 w-3.5 ${loadingRuns ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label>Run</Label>
            <Select value={selectedRunId} onValueChange={setSelectedRunId}>
              <SelectTrigger>
                <SelectValue placeholder="Select a run…" />
              </SelectTrigger>
              <SelectContent>
                {runs.map((r) => (
                  <SelectItem key={r.run_id} value={r.run_id}>
                    <span className="font-mono text-xs text-muted-foreground">{r.run_id.slice(0, 8)}…</span>
                    {" — "}
                    <span>{r.query_preview.replace(/#{1,6}\s/g, "").replace(/\*\*/g, "")}</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Run detail */}
          {runDetail && (
            <div className="rounded-lg border p-4 space-y-3 bg-muted/30">
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground font-mono">{runDetail.run_id}</p>
                <Markdown className="prose prose-sm prose-invert max-w-none" showCopy>{runDetail.query}</Markdown>
                <p className="text-xs text-muted-foreground">Audience: {runDetail.audience} · Language: {runDetail.language ?? "darija"}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                {Object.entries(runDetail.checkpoints).map(([step, cp]) => (
                  <Badge key={step} variant={cp.done ? "default" : "outline"} className="text-xs">
                    {cp.done ? "✅" : "⬜"} Step {step} — {cp.name}
                  </Badge>
                ))}
                <Badge variant={runDetail.has_scene ? "default" : "outline"} className="text-xs">
                  {runDetail.has_scene ? "✅" : "⬜"} generated_scene.py
                </Badge>
              </div>
              {runDetail.has_video && (
                <VideoPlayer videoUrl={runDetail.video_url} />
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Resume options */}
      {selectedRunId && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Resume Options</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-4 flex-wrap items-end">
              <div className="space-y-1.5">
                <Label>Resume from Step</Label>
                <Select value={fromStep} onValueChange={setFromStep}>
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
              <div className="flex items-center gap-2 pb-1">
                <Checkbox
                  id="copy-run"
                  checked={copyRun}
                  onCheckedChange={(v) => setCopyRun(!!v)}
                />
                <Label htmlFor="copy-run" className="cursor-pointer">
                  Copy to new run (non-destructive)
                </Label>
              </div>
            </div>

            <Separator />

            <Accordion type="single" collapsible>
              <AccordionItem value="nudges">
                <AccordionTrigger className="text-sm">Per-step nudges (optional)</AccordionTrigger>
                <AccordionContent>
                  <div className="space-y-3 pt-2">
                    {([1, 2, 3, 4, 5] as const).map((step) => (
                      <div key={step} className="space-y-1.5">
                        <Label className="text-xs">Step {step} — {STEP_LABELS[step]}</Label>
                        <Input
                          placeholder={`Nudge for step ${step}…`}
                          value={nudges[step]}
                          onChange={(e) => setNudges((n) => ({ ...n, [step]: e.target.value }))}
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
                      placeholder="Describe what to fix in the Manim scene…"
                      rows={3}
                      value={forceFix}
                      onChange={(e) => setForceFix(e.target.value)}
                      className="resize-none"
                    />
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">Screenshot of the issue (optional)</Label>
                      <Input
                        ref={imageInputRef}
                        type="file"
                        accept="image/*"
                        onChange={handleImageUpload}
                        disabled={uploadingImage}
                        className="text-xs cursor-pointer"
                      />
                      {uploadingImage && <p className="text-xs text-muted-foreground">Uploading…</p>}
                      {forceFixImagePreview && !uploadingImage && (
                        <div className="relative">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={forceFixImagePreview} alt="Fix screenshot" className="max-h-48 rounded border border-zinc-700 object-contain" />
                          <button
                            type="button"
                            onClick={() => { setForceFixImagePreview(null); setForceFixImagePath(null); if (imageInputRef.current) imageInputRef.current.value = ""; }}
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
              modelProvider={modelProvider}
              ttsProvider={ttsProvider}
              language={language}
              onModelChange={setModelProvider}
              onTtsChange={setTtsProvider}
              onLanguageChange={setLanguage}
            />

            <div className="flex gap-3 pt-1">
              <Button onClick={handleResume} disabled={running} className="gap-2">
                {running ? (
                  <><Loader2 className="h-4 w-4 animate-spin" /> Running…</>
                ) : (
                  <><Play className="h-4 w-4" /> Resume</>
                )}
              </Button>
              {running && (
                <Button variant="outline" onClick={stop} className="gap-2">
                  <Square className="h-4 w-4" /> Stop
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {error && (
        <Card className="border-destructive">
          <CardContent className="pt-4">
            <p className="text-destructive text-sm font-mono">{error}</p>
          </CardContent>
        </Card>
      )}

      <LogStream logs={logs} />
      <VideoPlayer videoUrl={videoUrl} />
    </div>
  );
}
