import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";

import type { ApiErrorBody } from "@/types";

export function readApiBaseUrl(): string {
  if (typeof localStorage !== "undefined") {
    const stored = localStorage.getItem("tutorial_api_base");
    if (stored && stored.trim().length > 0) {
      return stored.replace(/\/$/, "");
    }
  }
  return import.meta.env.VITE_API_URL?.replace(/\/$/, "") || "http://localhost:8000/api/v1";
}

/** Resolve API base for WebSocket construction (supports relative bases like ``/api/v1``). */
export function resolvePublicApiUrl(apiBase: string): URL {
  const b = apiBase.replace(/\/$/, "");
  if (b.startsWith("http://") || b.startsWith("https://")) {
    return new URL(b);
  }
  const origin =
    typeof window !== "undefined" && window.location?.origin
      ? window.location.origin
      : "http://localhost";
  const path = b.startsWith("/") ? b : `/${b}`;
  return new URL(path, origin);
}

export const api = axios.create({
  baseURL: readApiBaseUrl(),
  timeout: 30_000,
  headers: {
    "Content-Type": "application/json",
  },
});

function readApiKey(): string {
  return (
    import.meta.env.VITE_API_KEY ||
    (typeof localStorage !== "undefined" ? localStorage.getItem("tutorial_api_key") : null) ||
    "tutorial-demo-key"
  );
}

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  config.baseURL = readApiBaseUrl();
  const key = readApiKey();
  config.headers.set("X-API-Key", key);
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (error: AxiosError<ApiErrorBody>) => {
    const body = error.response?.data;
    const message = body?.detail || error.message || "Request failed";
    return Promise.reject(new Error(message));
  },
);

export function setStoredApiKey(key: string): void {
  localStorage.setItem("tutorial_api_key", key);
}

export function getStoredApiKey(): string | null {
  return localStorage.getItem("tutorial_api_key");
}

export function setStoredApiBase(url: string): void {
  localStorage.setItem("tutorial_api_base", url.replace(/\/$/, ""));
}

export function getStoredApiBase(): string | null {
  return localStorage.getItem("tutorial_api_base");
}
