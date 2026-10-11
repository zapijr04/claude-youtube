import { useState } from "react";
import HomeScreen from "./screens/HomeScreen";
import ImportScreen from "./screens/ImportScreen";
import StoryboardScreen from "./screens/StoryboardScreen";
import EditorScreen from "./screens/EditorScreen";
import VoiceStudioScreen from "./screens/VoiceStudioScreen";
import MotionStudioScreen from "./screens/MotionStudioScreen";
import SkillsLabScreen from "./screens/SkillsLabScreen";
import MemoryScreen from "./screens/MemoryScreen";
import ComputeScreen from "./screens/ComputeScreen";
import ExportScreen from "./screens/ExportScreen";
import SettingsScreen from "./screens/SettingsScreen";

const SCREENS = [
  { id: "home", label: "Home / Projects" },
  { id: "import", label: "Import & Analyze" },
  { id: "storyboard", label: "Storyboard / Script" },
  { id: "editor", label: "Editor" },
  { id: "voice", label: "Voice Studio" },
  { id: "motion", label: "Motion Studio" },
  { id: "skills", label: "Skills Lab" },
  { id: "memory", label: "Memory" },
  { id: "compute", label: "Compute / GPU" },
  { id: "export", label: "Export" },
  { id: "settings", label: "Settings" },
] as const;

type ScreenId = (typeof SCREENS)[number]["id"];

export default function App() {
  const [screen, setScreen] = useState<ScreenId>("home");
  const [projectId, setProjectId] = useState<string | null>(null);
  const [mediaId, setMediaId] = useState<string | null>(null);

  const ctx = { projectId, setProjectId, mediaId, setMediaId, navigate: setScreen };

  return (
    <>
      <nav className="sidebar">
        <div className="brand">NOOBZY AI STUDIO</div>
        {SCREENS.map((s) => (
          <div
            key={s.id}
            className={`nav-item ${screen === s.id ? "active" : ""}`}
            onClick={() => setScreen(s.id)}
          >
            {s.label}
          </div>
        ))}
      </nav>
      <main className="main">
        {screen === "home" && <HomeScreen {...ctx} />}
        {screen === "import" && <ImportScreen {...ctx} />}
        {screen === "storyboard" && <StoryboardScreen {...ctx} />}
        {screen === "editor" && <EditorScreen {...ctx} />}
        {screen === "voice" && <VoiceStudioScreen {...ctx} />}
        {screen === "motion" && <MotionStudioScreen {...ctx} />}
        {screen === "skills" && <SkillsLabScreen {...ctx} />}
        {screen === "memory" && <MemoryScreen {...ctx} />}
        {screen === "compute" && <ComputeScreen {...ctx} />}
        {screen === "export" && <ExportScreen {...ctx} />}
        {screen === "settings" && <SettingsScreen {...ctx} />}
      </main>
    </>
  );
}

export interface ScreenProps {
  projectId: string | null;
  setProjectId: (id: string | null) => void;
  mediaId: string | null;
  setMediaId: (id: string | null) => void;
  navigate: (screen: ScreenId) => void;
}
