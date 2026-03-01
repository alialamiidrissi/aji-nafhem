"use client";

import { useState, useCallback, useRef } from "react";

interface SSEState {
  logs: string;
  running: boolean;
  videoUrl: string | null;
  runId: string | null;
  error: string | null;
}

export function useSSE() {
  const [state, setState] = useState<SSEState>({
    logs: "",
    running: false,
    videoUrl: null,
    runId: null,
    error: null,
  });
  const abortRef = useRef<AbortController | null>(null);

  const start = useCallback(
    async (url: string, body: Record<string, unknown>) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setState({ logs: "", running: true, videoUrl: null, runId: null, error: null });

      try {
        const res = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          signal: controller.signal,
        });

        if (!res.ok || !res.body) {
          const text = await res.text().catch(() => "Unknown error");
          setState((s) => ({ ...s, running: false, error: text }));
          return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          // Parse SSE events from buffer
          const parts = buffer.split("\n\n");
          buffer = parts.pop() ?? "";

          for (const part of parts) {
            const lines = part.split("\n");
            let eventType = "message";
            let dataLines: string[] = [];

            for (const line of lines) {
              if (line.startsWith("event: ")) {
                eventType = line.slice(7).trim();
              } else if (line.startsWith("data: ")) {
                dataLines.push(line.slice(6));
              }
            }

            const data = dataLines.join("\n");
            if (!data) continue;

            if (eventType === "message") {
              setState((s) => ({ ...s, logs: s.logs + data + "\n" }));
            } else if (eventType === "video") {
              setState((s) => ({ ...s, videoUrl: data }));
            } else if (eventType === "run_id") {
              setState((s) => ({ ...s, runId: data }));
            } else if (eventType === "error") {
              setState((s) => ({ ...s, error: data }));
            } else if (eventType === "done") {
              setState((s) => ({ ...s, running: false }));
            }
          }
        }

        setState((s) => ({ ...s, running: false }));
      } catch (err: unknown) {
        if ((err as Error).name !== "AbortError") {
          setState((s) => ({
            ...s,
            running: false,
            error: (err as Error).message,
          }));
        }
      }
    },
    []
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setState((s) => ({ ...s, running: false }));
  }, []);

  return { ...state, start, stop };
}
