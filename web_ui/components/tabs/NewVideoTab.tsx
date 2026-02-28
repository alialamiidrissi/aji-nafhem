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
import { useSSE } from "@/hooks/useSSE";
import { Loader2, Play, Square } from "lucide-react";

const API_BASE = "http://localhost:8080";

export function NewVideoTab() {
  const [query, setQuery] = useState("");
  const [audience, setAudience] = useState("high school student");
  const [modelProvider, setModelProvider] = useState("google");
  const [ttsProvider, setTtsProvider] = useState("local");
  const { logs, running, videoUrl, error, start, stop } = useSSE();

  const handleGenerate = () => {
    if (!query.trim()) return;
    start(`${API_BASE}/api/generate`, {
      query,
      audience,
      model_provider: modelProvider,
      tts_provider: ttsProvider,
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
            onModelChange={setModelProvider}
            onTtsChange={setTtsProvider}
          />

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
