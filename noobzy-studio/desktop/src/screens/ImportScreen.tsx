import { useState } from "react";
import { api, SourceMedia } from "../lib/api";
import { ScreenProps } from "../App";

export default function ImportScreen({ projectId, setMediaId, navigate }: ScreenProps) {
  const [media, setMedia] = useState<SourceMedia | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cuts, setCuts] = useState<number[] | null>(null);
  const [script, setScript] = useState("");
  const [autoStyle, setAutoStyle] = useState(true);

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
      const result: any = await api.analyze(projectId, media.id, {
        narrationScript: script,
        autoStyle,
      });
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
      <p className="subtitle">
        Upload your gameplay, optionally paste what actually happened, and click one button --
        real cuts get detected, your script (if any) is timed across them, and generic
        editorial motion/transition SFX get applied automatically. No AI invents what's on
        screen; it only times and paces what you tell it.
      </p>
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

          <h2>Narration script (optional)</h2>
          <p className="subtitle">
            You recorded it, so you know what happened -- paste or write a rough account here
            and it gets split across the real detected scenes automatically (longer scenes get
            more of the script). Leave blank to fill narration in later per-scene.
          </p>
          <textarea
            value={script}
            onChange={(e) => setScript(e.target.value)}
            placeholder="I tried to rob every player on this server. First I scoped out a target..."
            rows={6}
            style={{ width: "100%", background: "var(--bg-panel-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 6, padding: 10, fontSize: 13, fontFamily: "inherit" }}
          />

          <div style={{ marginTop: 10 }}>
            <label style={{ fontSize: 13 }}>
              <input type="checkbox" checked={autoStyle} onChange={(e) => setAutoStyle(e.target.checked)} />
              {" "}Auto-apply editorial rhythm (transition SFX + zoom/shake keyed off real cut timing)
            </label>
          </div>

          <div style={{ marginTop: 14 }}>
            <button onClick={analyze}>{busy ? "Working..." : "Detect Scenes & Build Rough Cut"}</button>
          </div>
        </div>
      )}

      {cuts && (
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>Detected Scene Cuts</h2>
          <p className="subtitle">{cuts.length} real cut points found (ffmpeg scene filter, not guessed).</p>
          <div>{cuts.map((c) => <span key={c} className="badge" style={{ marginRight: 6 }}>{c.toFixed(1)}s</span>)}</div>
          <div style={{ marginTop: 14, display: "flex", gap: 10 }}>
            <button onClick={() => navigate("storyboard")}>Review Storyboard</button>
            <button className="secondary" onClick={() => navigate("editor")}>Skip to Editor (Preview / Export)</button>
          </div>
        </div>
      )}
    </div>
  );
}
