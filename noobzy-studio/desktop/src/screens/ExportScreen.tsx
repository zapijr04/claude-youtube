import { useState } from "react";
import { api } from "../lib/api";
import { ScreenProps } from "../App";

export default function ExportScreen({ projectId, mediaId }: ScreenProps) {
  const [log, setLog] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  if (!projectId || !mediaId) {
    return (
      <div>
        <h1>Export</h1>
        <div className="requirement">Import media and render first.</div>
      </div>
    );
  }

  const run = async (label: string, fn: () => Promise<any>) => {
    setError(null);
    try {
      const r: any = await fn();
      setLog((l) => [`${label}: ${r.path}`, ...l]);
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div>
      <h1>Export</h1>
      <p className="subtitle">
        OTIO and FCPXML are round-trip verified by re-parsing the file right after writing it.
        DaVinci Resolve's own GUI import has <b>not</b> been tested in this environment -- there
        is no Resolve installation here.
      </p>

      <div className="panel" style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <button onClick={() => run("OTIO", () => api.exportOtio(projectId, mediaId))}>Export OTIO</button>
        <button onClick={() => run("FCPXML", () => api.exportFcpxml(projectId, mediaId))}>Export FCPXML</button>
        <button onClick={() => run("Selective SRT", () => api.exportSrt(projectId, "selective"))}>Export Selective SRT</button>
        <button onClick={() => run("Full SRT", () => api.exportSrt(projectId, "full"))}>Export Full SRT</button>
        <button onClick={() => run("Timeline JSON", () => api.exportTimelineJson(projectId))}>Export TimelineDocument.json</button>
      </div>

      {error && <div className="error-box">{error}</div>}

      {log.length > 0 && (
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>Export Log</h2>
          {log.map((l, i) => <div key={i} style={{ fontSize: 12, fontFamily: "monospace", marginBottom: 4 }}>{l}</div>)}
        </div>
      )}
    </div>
  );
}
