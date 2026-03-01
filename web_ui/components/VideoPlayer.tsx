"use client";

import { api } from "@/lib/api";

interface VideoPlayerProps {
  videoUrl: string | null;
}

export function VideoPlayer({ videoUrl }: VideoPlayerProps) {
  if (!videoUrl) return null;

  const src = videoUrl.startsWith("http") ? videoUrl : api.mediaUrl(videoUrl);

  return (
    <div className="mt-4 rounded-lg overflow-hidden border border-zinc-700 bg-zinc-900">
      <video
        key={src}
        controls
        className="w-full max-h-[480px]"
        src={src}
      >
        Your browser does not support the video tag.
      </video>
    </div>
  );
}
