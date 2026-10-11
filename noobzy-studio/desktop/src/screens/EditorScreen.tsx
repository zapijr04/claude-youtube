import { useState } from "react";
import { api } from "../lib/api";
import { ScreenProps } from "../App";

export default function EditorScreen({ projectId, mediaId }: ScreenProps) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [density, setDensity] = useState("balanced");

  if (!projectId || !mediaId) {
    return (
      <div>
        <h1>Editor</h1>
        <div className="requirement">Import media and run Analyze first -- this screen renders the real MP4 from the current TimelineDocument.</div>
      </div>
    );
  }

  const render = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.render(projectId, mediaId, density);
      setResult(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h1>Editor</h1>
      <p className="subtitle">Video player + timeline + property inspector. Render runs the full real pipeline: narration, SFX, mix, overlays, FFmpeg encode.</p>
      {error && <div className="error-box">{error}</div>}

      <div className="panel">
        <label>SFX density<br />
          <select value={density} onChange={(e) => setDensity(e.target.value)}>
            <option value="light">Light</option>
            <option value="balanced">Balanced</option>
            <option value="high-energy">High-energy</option>
          </select>
        </label>
        <div style={{ marginTop: 14 }}>
          <button disabled={busy} onClick={render}>{busy ? "Rendering..." : "Render Full Video"}</button>
        </div>
      </div>

      {result && (
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>Render Result</h2>
          <p style={{ fontSize: 13, wordBreak: "break-all" }}>Video: {result.video_path}</p>
          <video src={`file://${result.video_path}`} controls style={{ width: "100%", maxWidth: 640, borderRadius: 8 }} />
          <h2>Loudness QC</h2>
          <table>
            <tbody>
              <tr><td>Integrated LUFS</td><td>{result.loudness_report.integrated_lufs}</td></tr>
              <tr><td>True Peak (dBTP)</td><td>{result.loudness_report.true_peak_dbtp}</td></tr>
              <tr><td>Clipping detected</td><td>{result.loudness_report.clipping_detected ? "YES" : "no"}</td></tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
