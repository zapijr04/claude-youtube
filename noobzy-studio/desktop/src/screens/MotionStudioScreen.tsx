import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { ScreenProps } from "../App";

export default function MotionStudioScreen({ projectId }: ScreenProps) {
  const [timeline, setTimeline] = useState<any>(null);

  useEffect(() => {
    if (!projectId) return;
    api.getTimeline(projectId).then(setTimeline).catch(() => setTimeline(null));
  }, [projectId]);

  return (
    <div>
      <h1>Motion Studio</h1>
      <p className="subtitle">Zoom, shake, cutout overlays and graphics layers -- all real FFmpeg filter stages, previewed after render in the Editor.</p>
      {!projectId && <div className="requirement">No project selected.</div>}
      {timeline && (
        <>
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
