"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LogStream } from "@/components/LogStream";
import { VideoPlayer } from "@/components/VideoPlayer";
import { PipelineOptions } from "@/components/PipelineOptions";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { useSSE } from "@/hooks/useSSE";
import { STEP_LABELS } from "@/lib/api";
import { Loader2, Play, Square } from "lucide-react";

const API_BASE = "http://localhost:8080";

export function NewVideoTab() {
  const [query, setQuery] = useState("");
  const [audience, setAudience] = useState("high school student");
  const [modelProvider, setModelProvider] = useState("google");
  const [ttsProvider, setTtsProvider] = useState("local");
  const [language, setLanguage] = useState("darija");
  const [nudges, setNudges] = useState<Record<number, string>>({ 1: "", 2: "", 3: "", 4: "", 5: "" });
  const { logs, running, videoUrl, error, start, stop } = useSSE();

  const handleGenerate = () => {
    if (!query.trim()) return;
    start(`${API_BASE}/api/generate`, {
      query,
      audience,
      model_provider: modelProvider,
      tts_provider: ttsProvider,
      language,
      nudge_1: nudges[1],
      nudge_2: nudges[2],
      nudge_3: nudges[3],
      nudge_4: nudges[4],
      nudge_5: nudges[5],
    });
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">New Educational Video</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="query">Topic / Query</Label>
            <Textarea
              id="query"
              placeholder="e.g. Explain how a binary search tree works, with visual examples"
              rows={4}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="resize-none"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="audience">Target Audience</Label>
            <Input
              id="audience"
              value={audience}
              onChange={(e) => setAudience(e.target.value)}
              placeholder="e.g. high school student"
            />
          </div>

          <PipelineOptions
            modelProvider={modelProvider}
            ttsProvider={ttsProvider}
            language={language}
            onModelChange={setModelProvider}
            onTtsChange={setTtsProvider}
            onLanguageChange={setLanguage}
          />

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
          </Accordion>

          <div className="flex gap-3 pt-1">
            <Button
              onClick={handleGenerate}
              disabled={running || !query.trim()}
              className="gap-2"
            >
              {running ? (
                <><Loader2 className="h-4 w-4 animate-spin" /> Generating…</>
              ) : (
                <><Play className="h-4 w-4" /> Generate Video</>
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
