"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type Status = "idle" | "recording" | "transcribing" | "error";

export function useVoice() {
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string>("");
  const [ttsOn, setTtsOn] = useState<boolean>(true);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // load tts preference
  useEffect(() => {
    try {
      const v = window.localStorage.getItem("ro.tts");
      if (v != null) setTtsOn(v === "1");
    } catch {}
  }, []);
  useEffect(() => {
    try { window.localStorage.setItem("ro.tts", ttsOn ? "1" : "0"); } catch {}
  }, [ttsOn]);

  const start = useCallback(async (): Promise<void> => {
    setError("");
    if (status === "recording") return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const mr = new MediaRecorder(stream, { mimeType: mime });
      chunksRef.current = [];
      mr.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      mr.start();
      mediaRef.current = mr;
      setStatus("recording");
    } catch (e) {
      setError(String(e));
      setStatus("error");
    }
  }, [status]);

  const stop = useCallback(async (): Promise<string> => {
    return new Promise((resolve) => {
      const mr = mediaRef.current;
      if (!mr) return resolve("");
      mr.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: mr.mimeType });
        chunksRef.current = [];
        mr.stream.getTracks().forEach((t) => t.stop());
        setStatus("transcribing");
        try {
          const fd = new FormData();
          fd.append("audio", blob, "audio.webm");
          const r = await fetch("/api/voice/transcribe", { method: "POST", body: fd });
          if (!r.ok) throw new Error(await r.text());
          const { text } = (await r.json()) as { text: string };
          setStatus("idle");
          resolve(text || "");
        } catch (e) {
          setError(String(e));
          setStatus("error");
          resolve("");
        }
      };
      mr.stop();
    });
  }, []);

  const cancel = useCallback(() => {
    const mr = mediaRef.current;
    if (mr && mr.state !== "inactive") {
      mr.stream.getTracks().forEach((t) => t.stop());
      try { mr.stop(); } catch {}
    }
    chunksRef.current = [];
    setStatus("idle");
  }, []);

  const speak = useCallback(async (text: string) => {
    if (!ttsOn || !text.trim()) return;
    try {
      const r = await fetch("/api/voice/speak", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!r.ok) return;
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      if (audioRef.current) {
        audioRef.current.pause();
        URL.revokeObjectURL(audioRef.current.src);
      }
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.play().catch(() => null);
    } catch {
      // silent — tts is best-effort
    }
  }, [ttsOn]);

  const stopSpeaking = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      try { URL.revokeObjectURL(audioRef.current.src); } catch {}
      audioRef.current = null;
    }
  }, []);

  return { status, error, start, stop, cancel, speak, stopSpeaking, ttsOn, setTtsOn };
}
