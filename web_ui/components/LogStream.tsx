"use client";

import { useEffect, useRef } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";

interface LogStreamProps {
  logs: string;
  className?: string;
}

export function LogStream({ logs, className = "" }: LogStreamProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  if (!logs) return null;

  return (
    <ScrollArea className={`h-72 rounded-md border bg-zinc-950 ${className}`}>
      <pre className="p-4 text-xs text-green-400 font-mono whitespace-pre-wrap break-words leading-relaxed">
        {logs}
      </pre>
      <div ref={bottomRef} />
    </ScrollArea>
  );
}
