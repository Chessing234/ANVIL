import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { SocShellProvider } from "@/context/soc-shell";

import App from "./App";
import "./index.css";

const baseUrl = import.meta.env.BASE_URL || "/";
const routerBasename =
  baseUrl === "/" ? undefined : baseUrl.replace(/\/$/, "") || undefined;

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <BrowserRouter basename={routerBasename}>
      <SocShellProvider>
        <App />
      </SocShellProvider>
    </BrowserRouter>
  </StrictMode>,
);
