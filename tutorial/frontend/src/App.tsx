import { Navigate, Route, Routes } from "react-router-dom";

import { EducationRealtime } from "@/components/EducationRealtime";
import { Layout } from "@/components/Layout";
import { Credentials } from "@/pages/Credentials";
import { Dashboard } from "@/pages/Dashboard";
import { Incidents } from "@/pages/Incidents";
import { Investigation } from "@/pages/Investigation";
import { Learn } from "@/pages/Learn";
import { PlayLesson } from "@/pages/PlayLesson";
import { Profile } from "@/pages/Profile";
import { Sandbox } from "@/pages/Sandbox";
import { Settings } from "@/pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="incidents" element={<Incidents />} />
        <Route path="investigations/:incidentId" element={<Investigation />} />
        <Route path="settings" element={<Settings />} />
        <Route element={<EducationRealtime />}>
          <Route path="learn" element={<Learn />} />
          <Route path="learn/:lessonId" element={<PlayLesson />} />
          <Route path="sandbox" element={<Sandbox />} />
          <Route path="profile" element={<Profile />} />
          <Route path="credentials" element={<Credentials />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
