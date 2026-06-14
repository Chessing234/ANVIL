import { Outlet } from "react-router-dom";
import { useEffect } from "react";

import { learnProgressClient } from "@/api/educationSockets";

/** Keeps learn-progress WebSocket warm for catalog, lessons, and profile views. */
export function EducationRealtime() {
  useEffect(() => {
    learnProgressClient.connect();
    return () => learnProgressClient.disconnect();
  }, []);
  return <Outlet />;
}
