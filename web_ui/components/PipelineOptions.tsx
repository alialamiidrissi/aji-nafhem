"use client";

import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SUPPORTED_LANGUAGES } from "@/lib/api";

interface PipelineOptionsProps {
  modelProvider: string;
  ttsProvider: string;
  language: string;
  onModelChange: (v: string) => void;
  onTtsChange: (v: string) => void;
  onLanguageChange: (v: string) => void;
}

export function PipelineOptions({
  modelProvider,
  ttsProvider,
  language,
  onModelChange,
  onTtsChange,
  onLanguageChange,
}: PipelineOptionsProps) {
  return (
    <div className="flex gap-4 flex-wrap">
      <div className="flex flex-col gap-1.5">
        <Label>Language</Label>
        <Select value={language} onValueChange={onLanguageChange}>
          <SelectTrigger className="w-52">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SUPPORTED_LANGUAGES.map((l) => (
              <SelectItem key={l.value} value={l.value}>
                {l.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label>Model Provider</Label>
        <Select value={modelProvider} onValueChange={onModelChange}>
          <SelectTrigger className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="google">Google (Gemini)</SelectItem>
            <SelectItem value="openai">OpenAI</SelectItem>
            <SelectItem value="openrouter">OpenRouter</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label>TTS Provider</Label>
        <Select value={ttsProvider} onValueChange={onTtsChange}>
          <SelectTrigger className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="local">Local (Coqui XTTS)</SelectItem>
            <SelectItem value="elevenlabs">ElevenLabs</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
