import { ScreenProps } from "../App";
import { API_BASE } from "../lib/api";

export default function SettingsScreen(_: ScreenProps) {
  return (
    <div>
      <h1>Settings</h1>
      <p className="subtitle">Credentials and provider configuration live in the backend's .env (see .env.example). Nothing here is sent anywhere until you opt in.</p>

      <div className="panel">
        <h2 style={{ marginTop: 0 }}>Backend</h2>
        <p style={{ fontSize: 13 }}>API base: <code>{API_BASE}</code></p>
      </div>

      <div className="panel">
        <h2 style={{ marginTop: 0 }}>Provider Credentials (backend .env)</h2>
        <table>
          <thead><tr><th>Variable</th><th>Purpose</th></tr></thead>
          <tbody>
            <tr><td>ELEVENLABS_API_KEY</td><td>Real narration via ElevenLabs text-to-speech-with-timestamps</td></tr>
            <tr><td>ELEVENLABS_VOICE_ID</td><td>Voice to use for narration</td></tr>
            <tr><td>LLM_API_KEY</td><td>Optional: scene-understanding / script-writing LLM provider</td></tr>
            <tr><td>RUNPOD_API_KEY</td><td>Optional: paid cloud GPU jobs (gated behind explicit cost approval)</td></tr>
            <tr><td>COMFYUI_URL</td><td>Optional: local ComfyUI instance for AI image/video workflows</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
