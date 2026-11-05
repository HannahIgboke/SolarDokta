"use client";
// Phone alerts (Web Push): ask permission, subscribe this browser with our public key, and tell
// the backend where to send. Works in Chrome/Edge/Firefox/Samsung Internet on Android and
// computers, and on iPhone (iOS 16.4+) once SolarDokta is added to the Home Screen.
import { api } from "./api";

export type PushState = "unsupported" | "ios-install" | "blocked" | "off" | "on";

export function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true;
}

export function isIos(): boolean {
  return typeof navigator !== "undefined" && /iphone|ipad|ipod/i.test(navigator.userAgent);
}

function supported(): boolean {
  return typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

export async function registration(): Promise<ServiceWorkerRegistration | null> {
  if (!supported()) return null;
  return (await navigator.serviceWorker.getRegistration()) ?? navigator.serviceWorker.register("/sw.js");
}

export async function pushState(): Promise<PushState> {
  if (isIos() && !isStandalone()) return "ios-install";
  if (!supported()) return "unsupported";
  if (Notification.permission === "denied") return "blocked";
  const reg = await registration();
  const sub = await reg?.pushManager.getSubscription();
  return sub ? "on" : "off";
}

function keyBytes(b64: string): Uint8Array<ArrayBuffer> {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

export async function turnOn(lang: string): Promise<PushState> {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return permission === "denied" ? "blocked" : "off";
  const { key } = await api<{ key: string | null }>("/api/push/key");
  if (!key) throw new Error("Alerts aren't set up on the server yet.");
  const reg = await registration();
  if (!reg) return "unsupported";
  await navigator.serviceWorker.ready;
  let sub: PushSubscription;
  try {
    sub = (await reg.pushManager.getSubscription()) ?? await Promise.race([
      reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key) }),
      new Promise<never>((_, no) => setTimeout(() => no(new Error("timeout")), 20000)),
    ]);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "";
    throw new Error(msg === "timeout"
      ? "Your phone's notification service didn't answer. Check your internet and try again."
      : "This browser couldn't turn on alerts. Private or incognito windows can't get alerts; open SolarDokta in a normal window or install it, then try again.");
  }
  const json = sub.toJSON();
  await api("/api/push/subscribe", { method: "POST", body: JSON.stringify({ endpoint: json.endpoint, keys: json.keys, lang }) });
  return "on";
}

export async function turnOff(): Promise<PushState> {
  const sub = await (await registration())?.pushManager.getSubscription();
  if (sub) {
    await api("/api/push/unsubscribe", { method: "POST", body: JSON.stringify({ endpoint: sub.endpoint }) }).catch(() => undefined);
    await sub.unsubscribe();
  }
  return "off";
}

export async function sendTest(): Promise<void> {
  const sub = await (await registration())?.pushManager.getSubscription();
  if (!sub) throw new Error("Turn on alerts first.");
  await api("/api/push/test", { method: "POST", body: JSON.stringify({ endpoint: sub.endpoint }) });
}
