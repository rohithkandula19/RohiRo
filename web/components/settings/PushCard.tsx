"use client";

import { useEffect, useState } from "react";

function urlBase64ToUint8Array(base64: string) {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(b64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

export function PushCard() {
  const [state, setState] = useState<"unknown" | "unsupported" | "off" | "on" | "error">("unknown");
  const [detail, setDetail] = useState("");

  useEffect(() => {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      setState("unsupported");
      return;
    }
    navigator.serviceWorker.getRegistration().then(async (reg) => {
      const sub = await reg?.pushManager.getSubscription();
      setState(sub ? "on" : "off");
    });
  }, []);

  async function enable() {
    try {
      const keyRes = await fetch("/api/push/vapid-public");
      if (!keyRes.ok) {
        setState("error");
        setDetail("push keys not generated. run: uv run python -m api.integrations.webpush --generate");
        return;
      }
      const { key } = await keyRes.json();
      const reg = await navigator.serviceWorker.register("/sw.js");
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(key),
      });
      const save = await fetch("/api/push/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(sub.toJSON()),
      });
      setState(save.ok ? "on" : "error");
      if (!save.ok) setDetail("subscribe save failed");
    } catch (e: any) {
      setState("error");
      setDetail(String(e?.message || e));
    }
  }

  async function test() {
    await fetch("/api/push/test", { method: "POST" });
  }

  return (
    <div className="card max-w-2xl">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[13px] text-ink">notifications</div>
          <div className="text-[12px] text-ink-muted">
            {state === "unsupported" && "this browser does not support web push."}
            {state === "off" && "get pinged when an approval needs you or the digest is ready."}
            {state === "on" && "push is on for this browser."}
            {state === "error" && (detail || "something went wrong.")}
            {state === "unknown" && "checking…"}
          </div>
        </div>
        <div className="flex gap-2">
          {state === "off" && (
            <button className="btn" onClick={enable}>
              enable
            </button>
          )}
          {state === "on" && (
            <button className="btn" onClick={test}>
              test
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
