import { useEffect, useState } from "react";

import { getStoredApiBase, getStoredApiKey, readApiBaseUrl, setStoredApiBase, setStoredApiKey } from "@/api/client";
import * as systemApi from "@/api/system";
import { wsClient } from "@/api/websocket";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";

export function Settings() {
  const [base, setBase] = useState(readApiBaseUrl());
  const [key, setKey] = useState(() => getStoredApiKey() ?? (import.meta.env.VITE_API_KEY as string | undefined) ?? "");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const stored = getStoredApiBase();
    if (stored) setBase(stored);
  }, []);

  const save = () => {
    setStoredApiBase(base);
    setStoredApiKey(key);
    wsClient.disconnect();
    wsClient.connect();
    setNotice("Configuration persisted. WebSocket client re-opened with the new base URL.");
    setError(null);
  };

  const probe = async () => {
    setError(null);
    setNotice(null);
    try {
      const h = await systemApi.getHealth();
      setNotice(`Health check OK — status ${h.status} @ ${h.timestamp}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Health check failed");
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-50">System settings</h1>
        <p className="text-sm text-slate-400">
          Override API base URL and API key for Splunk / UiPath demos. Values persist in <code>localStorage</code> and
          take effect on the next request.
        </p>
      </div>

      {notice ? (
        <Alert>
          <AlertTitle>Update</AlertTitle>
          <AlertDescription>{notice}</AlertDescription>
        </Alert>
      ) : null}
      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Diagnostics</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>API connectivity</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label htmlFor="base" className="text-sm font-medium text-slate-200">
              Base URL
            </label>
            <Input id="base" value={base} onChange={(e) => setBase(e.target.value)} placeholder="http://localhost:8000/api/v1" />
            <p className="text-xs text-slate-500">
              Defaults to <code className="text-slate-400">VITE_API_URL</code> when unset. Include the{" "}
              <code className="text-slate-400">/api/v1</code> prefix to match the FastAPI mount.
            </p>
          </div>
          <div className="space-y-2">
            <label htmlFor="key" className="text-sm font-medium text-slate-200">
              API key
            </label>
            <Input id="key" type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="tutorial-demo-key" />
            <p className="text-xs text-slate-500">Sent as <code className="text-slate-400">X-API-Key</code> on every REST call.</p>
          </div>
          <Separator />
          <div className="flex flex-wrap gap-2">
            <Button onClick={save}>Save & reconnect WS</Button>
            <Button variant="secondary" onClick={() => void probe()}>
              Test health endpoint
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
