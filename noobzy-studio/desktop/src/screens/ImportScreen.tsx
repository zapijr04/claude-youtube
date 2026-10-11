import { useState } from "react";
import { api, SourceMedia } from "../lib/api";
import { ScreenProps } from "../App";

export default function ImportScreen({ projectId, setMediaId, navigate }: ScreenProps) {
  const [media, setMedia] = useState<SourceMedia | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cuts, setCuts] = useState<number[] | null>(null);

  if (!projectId) {
    return (
      <div>
        <h1>Import &amp; Analyze</h1>
        <div className="requirement">No project selected. Go to Home and create or open a project first.</div>
      </div>
    );
  }

  const onFile = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      const m = await api.importMedia(projectId, file);
      setMedia(m);
      setMediaId(m.id);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const analyze = async () => {
    if (!media) return;
    setBusy(true);
    setError(null);
    try {
      const result: any = await api.analyze(projectId, media.id);
      setCuts(result.detected_cuts);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h1>Import &amp; Analyze</h1>
      <p className="subtitle">FFprobe validates the file; FFmpeg's real scene-cut detector finds candidate edit windows.</p>
      {error && <div className="error-box">{error}</div>}

      <div className="panel">
        <input
          type="file"
          accept="video/mp4,video/quicktime,video/mov"
          onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
        />
        {busy && <p className="subtitle">Working...</p>}
      </div>

      {media && (
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>Media</h2>
          <table>
            <tbody>
              <tr><td>Codec</td><td>{media.codec}</td></tr>
              <tr><td>Resolution</td><td>{media.width}x{media.height}</td></tr>
              <tr><td>FPS</td><td>{media.fps}</td></tr>
              <tr><td>Duration</td><td>{media.duration_sec.toFixed(1)}s</td></tr>
              <tr><td>Audio</td><td>{media.has_audio ? "yes" : "no"}</td></tr>
            </tbody>
          </table>
          {media.thumbnails.length > 0 && (
            <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
              {media.thumbnails.map((t) => (
                <img key={t} src={`file://${t}`} width={100} style={{ borderRadius: 4, border: "1px solid var(--border)" }} />
              ))}
            </div>
          )}
          <div style={{ marginTop: 14 }}>
            <button onClick={analyze}>Detect Scenes &amp; Build Rough Cut</button>
          </div>
        </div>
      )}

      {cuts && (
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>Detected Scene Cuts</h2>
          <p className="subtitle">{cuts.length} real cut points found (ffmpeg scene filter, not guessed).</p>
          <div>{cuts.map((c) => <span key={c} className="badge" style={{ marginRight: 6 }}>{c.toFixed(1)}s</span>)}</div>
          <div style={{ marginTop: 14 }}>
            <button onClick={() => navigate("storyboard")}>Continue to Storyboard</button>
          </div>
        </div>
      )}
    </div>
  );
}
