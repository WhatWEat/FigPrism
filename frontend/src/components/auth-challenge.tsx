"use client";
import Script from "next/script";
import { useEffect, useRef, useState } from "react";

type Turnstile = {
  render: (node: HTMLElement, options: Record<string, unknown>) => string;
  remove: (id: string) => void;
};
declare global {
  interface Window {
    turnstile?: Turnstile;
  }
}
export function AuthChallenge({
  siteKey,
  action,
  onToken,
}: {
  siteKey: string;
  action: "login" | "register";
  onToken: (token: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const callback = useRef(onToken);
  callback.current = onToken;
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (window.turnstile) setReady(true);
  }, []);
  useEffect(() => {
    if (!ready || !container.current || !window.turnstile) return;
    callback.current("");
    setFailed(false);
    const widget = window.turnstile.render(container.current, {
      sitekey: siteKey,
      action,
      theme: "light",
      size: "flexible",
      callback: (token: string) => {
        setFailed(false);
        callback.current(token);
      },
      "expired-callback": () => callback.current(""),
      "error-callback": () => {
        callback.current("");
        setFailed(true);
      },
    });
    return () => {
      window.turnstile?.remove(widget);
      callback.current("");
    };
  }, [ready, siteKey, action, attempt]);
  return (
    <div className="auth-challenge">
      <Script
        src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit"
        strategy="afterInteractive"
        onReady={() => setReady(true)}
        onError={() => setFailed(true)}
      />
      <div ref={container} />
      {!ready && !failed && <p>正在加载人机验证…</p>}
      {failed && (
        <p role="alert">
          人机验证暂时不可用。
          <button
            type="button"
            className="text-button"
            onClick={() => {
              if (window.turnstile) setAttempt((n) => n + 1);
              else window.location.reload();
            }}
          >
            重新验证
          </button>
        </p>
      )}
    </div>
  );
}
