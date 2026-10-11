import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { ScreenProps } from "../App";

export default function MotionStudioScreen({ projectId }: ScreenProps) {
  const [timeline, setTimeline] = useState<any>(null);
  const [rampRate, setRampRate] = useState(2.0);
  const [error, setError] = useState<string | null>(null);

  const refresh = () => {
    if (!projectId) return;
    api.getTimeline(projectId).then(setTimeline).catch(() => setTimeline(null));
  };
  useEffect(refresh, [projectId]);

  const applyRamp = async (sceneId: string) => {
    if (!projectId) return;
    setError(null);
    try {
      await api.speedRampScene(projectId, sceneId, rampRate);
      refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div>
      <h1>Motion Studio</h1>
      <p className="subtitle">Zoom, shake, cutout overlays and graphics layers -- all real FFmpeg filter stages, previewed in the Editor.</p>
      {!projectId && <div className="requirement">No project selected.</div>}
      {error && <div className="error-box">{error}</div>}
      {timeline && (
        <>
          <div className="panel">
            <h2 style={{ marginTop: 0 }}>Scenes &amp; Speed Ramp</h2>
            <p className="subtitle">
              Sets a scene's playback rate and automatically retimes every beat/caption/SFX
              cue that comes after it, so sync never drifts.
            </p>
            <label>Rate (&gt;1 = sped up, &lt;1 = slow motion)<br />
              <input type="number" step="0.1" value={rampRate} onChange={(e) => setRampRate(Number(e.target.value))} />
            </label>
            <table>
              <thead><tr><th>Scene</th><th>Source window</th><th>Playback rate</th><th></th></tr></thead>
              <tbody>
                {timeline.scenes.map((s: any) => (
                  <tr key={s.id}>
                    <td style={{ fontFamily: "monospace", fontSize: 11 }}>{s.id}</td>
                    <td>{s.source_in_sec.toFixed(1)}s - {s.source_out_sec.toFixed(1)}s</td>
                    <td>{s.playback_rate}x</td>
                    <td><button className="secondary" onClick={() => applyRamp(s.id)}>Apply ramp</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="panel">
            <h2 style={{ marginTop: 0 }}>Motion Presets</h2>
            {timeline.motion.length === 0 && <p className="subtitle">None yet -- add manual markers or use a creative brief to request motion.</p>}
            <table>
              <thead><tr><th>Kind</th><th>Window</th></tr></thead>
              <tbody>
                {timeline.motion.map((m: any) => (
                  <tr key={m.id}><td>{m.kind}</td><td>{m.output_start_sec.toFixed(1)}s - {m.output_end_sec.toFixed(1)}s</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="panel">
            <h2 style={{ marginTop: 0 }}>Graphics Layers</h2>
            <table>
              <thead><tr><th>Kind</th><th>Window</th><th>Params</th></tr></thead>
              <tbody>
                {timeline.graphics.map((g: any) => (
                  <tr key={g.id}><td>{g.kind}</td><td>{g.output_start_sec.toFixed(1)}s - {g.output_end_sec.toFixed(1)}s</td><td style={{ fontFamily: "monospace", fontSize: 11 }}>{JSON.stringify(g.params)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
