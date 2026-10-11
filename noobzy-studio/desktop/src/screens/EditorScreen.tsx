import { useState } from "react";
import { api } from "../lib/api";
import { ScreenProps } from "../App";

export default function EditorScreen({ projectId, mediaId }: ScreenProps) {
  const [previewBusy, setPreviewBusy] = useState(false);
  const [exportBusy, setExportBusy] = useState(false);
  const [preview, setPreview] = useState<any>(null);
  const [exportResult, setExportResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [density, setDensity] = useState("balanced");
  const [outputDir, setOutputDir] = useState("");

  if (!projectId || !mediaId) {
    return (
      <div>
        <h1>Editor</h1>
        <div className="requirement">Import media and run Analyze first -- this screen previews and exports the current TimelineDocument.</div>
      </div>
    );
  }

  const runPreview = async () => {
    setPreviewBusy(true);
    setError(null);
    try {
      const r = await api.preview(projectId, mediaId, density);
      setPreview(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setPreviewBusy(false);
    }
  };

  const runExport = async () => {
    setExportBusy(true);
    setError(null);
    try {
      const r = await api.exportFinalVideo(projectId, mediaId, {
        sfxDensity: density,
        outputDir: outputDir || undefined,
      });
      setExportResult(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setExportBusy(false);
    }
  };

  return (
    <div>
      <h1>Editor</h1>
      <p className="subtitle">
        Edits (cuts, captions, narration, SFX, mixing) live entirely in the saved project --
        <b> Preview</b> is a fast, cached, reused render that never touches your export folder.
        Only <b>Export Final Video</b> writes a finished MP4, exactly once, to the location you choose.
      </p>
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
          <button disabled={previewBusy} onClick={runPreview}>
            {previewBusy ? "Building preview..." : "Preview"}
          </button>
        </div>
      </div>

      {preview && (
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>Preview {preview.cached && <span className="badge ok">cached</span>}</h2>
          <p style={{ fontSize: 13, wordBreak: "break-all" }}>{preview.video_path}</p>
          <video src={`file://${preview.video_path}`} controls style={{ width: "100%", maxWidth: 640, borderRadius: 8 }} />

          <h2>Voice Coverage</h2>
          <p style={{ fontSize: 13 }}>
            Coverage: {(preview.voice_coverage_report.voice_coverage_ratio * 100).toFixed(1)}% --{" "}
            {preview.voice_coverage_report.gaps_over_threshold.length} gap(s) over{" "}
            {preview.voice_coverage_report.gap_threshold_sec}s
          </p>
          {preview.voice_coverage_report.gaps_over_threshold.length > 0 && (
            <table>
              <thead><tr><th>Start</th><th>End</th><th>Duration</th></tr></thead>
              <tbody>
                {preview.voice_coverage_report.gaps_over_threshold.map((g: any, i: number) => (
                  <tr key={i}><td>{g.start_sec}s</td><td>{g.end_sec}s</td><td>{g.duration_sec}s</td></tr>
                ))}
              </tbody>
            </table>
          )}

          <h2>Loudness QC</h2>
          <table>
            <tbody>
              <tr><td>Integrated LUFS</td><td>{preview.loudness_report.integrated_lufs}</td></tr>
              <tr><td>True Peak (dBTP)</td><td>{preview.loudness_report.true_peak_dbtp}</td></tr>
              <tr><td>Clipping detected</td><td>{preview.loudness_report.clipping_detected ? "YES" : "no"}</td></tr>
            </tbody>
          </table>
        </div>
      )}

      <div className="panel">
        <h2 style={{ marginTop: 0 }}>Export Final Video</h2>
        <p className="requirement">
          This is the only action that writes a finished MP4 to disk outside the app's cache.
          Leave the output folder blank to use the default project export folder.
        </p>
        <label>Output folder (optional)<br />
          <input type="text" style={{ width: "100%" }} placeholder="/path/to/output/folder"
            value={outputDir} onChange={(e) => setOutputDir(e.target.value)} />
        </label>
        <div style={{ marginTop: 14 }}>
          <button disabled={exportBusy} onClick={runExport}>
            {exportBusy ? "Rendering final video..." : "Export Final Video"}
          </button>
        </div>
      </div>

      {exportResult && (
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>Export Result</h2>
          <p style={{ fontSize: 13, wordBreak: "break-all" }}>{exportResult.video_path}</p>
          <p className="subtitle">New MP4 file(s) written: {exportResult.new_mp4_files_in_output_dir.length}</p>
          {exportResult.sidecars && (
            <p className="subtitle" style={{ fontSize: 12 }}>
              Also wrote: SRT, OTIO, FCPXML, timeline.json alongside the video.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
