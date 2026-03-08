"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";

const remarkPlugins = [remarkMath];
const rehypePlugins = [rehypeKatex];

export function Markdown({ children, className, showCopy }: { children: string; className?: string; showCopy?: boolean }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(children);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={`relative group ${className ?? ""}`}>
      {showCopy && (
        <Button
          size="sm"
          variant="ghost"
          onClick={handleCopy}
          className="absolute top-0 right-0 h-6 px-2 opacity-0 group-hover:opacity-100 transition-opacity text-zinc-400 hover:text-zinc-200 gap-1 z-10"
        >
          {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
          <span className="text-xs">{copied ? "Copied" : "Copy MD"}</span>
        </Button>
      )}
      <ReactMarkdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
