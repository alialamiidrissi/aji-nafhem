"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { HomeTab } from "@/components/tabs/HomeTab";
import { NewVideoTab } from "@/components/tabs/NewVideoTab";
import { ResumeRunTab } from "@/components/tabs/ResumeRunTab";
import { ProjectsTab } from "@/components/tabs/ProjectsTab";
import { Separator } from "@/components/ui/separator";
import { Home as HomeIcon, Video, RotateCcw, FolderOpen } from "lucide-react";

export default function Home() {
  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border/60 bg-background/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center text-white text-sm font-bold">
            أن
          </div>
          <div>
            <h1 className="text-lg font-semibold leading-none">أجي نفهم</h1>
            <p className="text-xs text-muted-foreground mt-0.5">Aji Nafhem — Educational Video Generator</p>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-5xl mx-auto px-4 py-8">
        <Tabs defaultValue="home" className="space-y-6">
          <TabsList className="grid w-full grid-cols-4 h-11">
            <TabsTrigger value="home" className="gap-2 text-sm">
              <HomeIcon className="h-4 w-4" />
              Home
            </TabsTrigger>
            <TabsTrigger value="new" className="gap-2 text-sm">
              <Video className="h-4 w-4" />
              New Video
            </TabsTrigger>
            <TabsTrigger value="resume" className="gap-2 text-sm">
              <RotateCcw className="h-4 w-4" />
              Resume Run
            </TabsTrigger>
            <TabsTrigger value="projects" className="gap-2 text-sm">
              <FolderOpen className="h-4 w-4" />
              Projects
            </TabsTrigger>
          </TabsList>

          <TabsContent value="home" className="mt-6">
            <HomeTab />
          </TabsContent>

          <TabsContent value="new" className="mt-6">
            <NewVideoTab />
          </TabsContent>

          <TabsContent value="resume" className="mt-6">
            <ResumeRunTab />
          </TabsContent>

          <TabsContent value="projects" className="mt-6">
            <ProjectsTab />
          </TabsContent>
        </Tabs>
      </main>

      <Separator className="mt-16" />
      <footer className="max-w-5xl mx-auto px-4 py-4 text-xs text-muted-foreground text-center">
        Aji Nafhem · Agentic pipeline powered by Gemini Flash + Coqui XTTS + Manim
      </footer>
    </div>
  );
}
