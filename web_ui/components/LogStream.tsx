"use client";

import { useEffect, useRef, useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Copy, Check } from "lucide-react";

interface LogStreamProps {
  logs: string;
  className?: string;
}

export function LogStream({ logs, className = "" }: LogStreamProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  if (!logs) return null;

  const handleCopy = async () => {
    await navigator.clipboard.writeText(logs);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={`rounded-md border bg-zinc-950 ${className}`}>
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-zinc-800">
        <span className="text-xs text-zinc-500 font-mono">logs</span>
        <Button
          size="sm"
          variant="ghost"
          onClick={handleCopy}
          className="h-6 px-2 text-zinc-400 hover:text-zinc-200 gap-1.5"
        >
          {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
          <span className="text-xs">{copied ? "Copied" : "Copy"}</span>
        </Button>
      </div>
      <ScrollArea className="h-72">
        <pre className="p-4 text-xs text-green-400 font-mono whitespace-pre-wrap break-words leading-relaxed">
          {logs}
        </pre>
        <div ref={bottomRef} />
      </ScrollArea>
    </div>
  );
}
