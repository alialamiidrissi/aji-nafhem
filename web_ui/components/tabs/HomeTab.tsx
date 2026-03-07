"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Video, RotateCcw, FolderOpen, Cpu, Mic, Map, Shapes, Code2, Film, ArrowRight } from "lucide-react";

const PIPELINE_STEPS = [
  {
    number: 1,
    icon: Cpu,
    label: "Analytical Solver",
    description: "Breaks down the topic into logical concepts and learning steps tailored to the target audience.",
    color: "text-violet-400",
    bg: "bg-violet-500/10 border-violet-500/20",
  },
  {
    number: 2,
    icon: Mic,
    label: "Script & TTS",
    description: "Writes a tightly-segmented voiceover script and synthesises audio via Coqui XTTS or ElevenLabs.",
    color: "text-sky-400",
    bg: "bg-sky-500/10 border-sky-500/20",
  },
  {
    number: 3,
    icon: Map,
    label: "Map Generator",
    description: "Generates geopolitical SVG maps when the topic requires geographic context.",
    color: "text-emerald-400",
    bg: "bg-emerald-500/10 border-emerald-500/20",
  },
  {
    number: 4,
    icon: Shapes,
    label: "SVG Assets",
    description: "Creates custom vector graphics and diagrams to illustrate key concepts visually.",
    color: "text-amber-400",
    bg: "bg-amber-500/10 border-amber-500/20",
  },
  {
    number: 5,
    icon: Code2,
    label: "Manim Code",
    description: "Generates Python/Manim animation code that syncs visuals frame-by-frame with the voiceover.",
    color: "text-rose-400",
    bg: "bg-rose-500/10 border-rose-500/20",
  },
  {
    number: 6,
    icon: Film,
    label: "Compile & Fix",
    description: "Renders the Manim scene to video, auto-detecting and retrying compile errors up to several times.",
    color: "text-teal-400",
    bg: "bg-teal-500/10 border-teal-500/20",
  },
];

const TABS_INFO = [
  {
    icon: Video,
    label: "New Video",
    value: "new",
    description: "Generate a complete educational video from scratch. Enter a topic, pick a language and audience, and the full 6-step pipeline runs automatically.",
    tips: ["Use specific queries for better results", "Add per-step nudges to guide the AI", "Choose between Darija, MSA, French, or English"],
    gradient: "from-emerald-500 to-teal-500",
  },
  {
    icon: RotateCcw,
    label: "Resume Run",
    value: "resume",
    description: "Pick up any previous single-scene run from where it left off. Useful when a step fails or when you want to regenerate only part of the pipeline.",
    tips: ["Resume from any step (1–6)", "Use Copy Run to keep the original intact", "Attach a screenshot to guide the force-fix prompt"],
    gradient: "from-sky-500 to-blue-500",
  },
  {
    icon: FolderOpen,
    label: "Projects",
    value: "projects",
    description: "Manage multi-scene projects. Build longer videos by adding, importing, or reordering scenes, then stitch them into a single final video.",
    tips: ["Fork a project to safely experiment", "Import scenes from existing runs", "Run individual scenes with custom step ranges"],
    gradient: "from-violet-500 to-purple-500",
  },
];

export function HomeTab() {
  return (
    <div className="space-y-12">
      {/* Hero */}
      <div className="text-center space-y-4 pt-4">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-600 text-white text-2xl font-bold shadow-lg shadow-emerald-500/20 mb-2">
          أن
        </div>
        <h2 className="text-3xl font-bold tracking-tight">Aji Nafhem</h2>
        <p className="text-muted-foreground max-w-xl mx-auto leading-relaxed">
          An agentic pipeline that turns any educational topic into a fully narrated,
          animated video — powered by Gemini Flash, Manim, and Coqui XTTS.
        </p>
      </div>

      {/* Workflow overview */}
      <section className="space-y-4">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">How it works</h3>
          <div className="flex-1 h-px bg-border" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {PIPELINE_STEPS.map((step, i) => {
            const Icon = step.icon;
            return (
              <Card key={step.number} className={`border ${step.bg} relative overflow-hidden`}>
                <CardContent className="pt-5 pb-4 px-5 space-y-2">
                  <div className="flex items-center gap-2.5">
                    <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold border ${step.bg} ${step.color}`}>
                      {step.number}
                    </div>
                    <Icon className={`h-4 w-4 ${step.color}`} />
                    <span className="text-sm font-semibold">{step.label}</span>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed pl-0.5">{step.description}</p>
                  {i < PIPELINE_STEPS.length - 1 && (
                    <ArrowRight className="absolute right-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/30 hidden lg:block" />
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      </section>

      {/* Tabs guide */}
      <section className="space-y-4">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">Tabs</h3>
          <div className="flex-1 h-px bg-border" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {TABS_INFO.map((tab) => {
            const Icon = tab.icon;
            return (
              <Card key={tab.value} className="border overflow-hidden">
                <div className={`h-1 w-full bg-gradient-to-r ${tab.gradient}`} />
                <CardContent className="pt-5 pb-5 px-5 space-y-3">
                  <div className="flex items-center gap-2">
                    <div className={`w-8 h-8 rounded-lg bg-gradient-to-br ${tab.gradient} flex items-center justify-center shadow-sm`}>
                      <Icon className="h-4 w-4 text-white" />
                    </div>
                    <span className="font-semibold text-base">{tab.label}</span>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed">{tab.description}</p>
                  <ul className="space-y-1.5">
                    {tab.tips.map((tip) => (
                      <li key={tip} className="flex items-start gap-1.5 text-xs text-muted-foreground">
                        <span className="mt-0.5 shrink-0 w-1 h-1 rounded-full bg-muted-foreground/50 translate-y-1.5" />
                        {tip}
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </section>

      {/* Quick tips */}
      <section className="space-y-4">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">Quick tips</h3>
          <div className="flex-1 h-px bg-border" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {[
            { label: "Nudges", text: "Each pipeline step accepts an optional free-text nudge to steer the AI's output without re-writing the prompt." },
            { label: "Force-fix", text: "If the Manim render looks wrong, paste a description (or screenshot) into the force-fix box and re-run from Step 6." },
            { label: "Projects vs Runs", text: "A Run is a single-scene artifact. A Project is a collection of scenes that can be stitched into one long video." },
            { label: "Forking", text: "Fork a project before making risky changes — the fork is a full copy with independent scenes and checkpoints." },
          ].map((tip) => (
            <div key={tip.label} className="flex gap-3 p-4 rounded-lg border bg-muted/20">
              <Badge variant="outline" className="shrink-0 h-fit mt-0.5">{tip.label}</Badge>
              <p className="text-xs text-muted-foreground leading-relaxed">{tip.text}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
