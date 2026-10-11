import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { ScreenProps } from "../App";

export default function VoiceStudioScreen({ projectId }: ScreenProps) {
  const [timeline, setTimeline] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState<string | null>(null);

  const refresh = () => {
    if (!projectId) return;
    api.getTimeline(projectId).then(setTimeline).catch(() => setTimeline(null));
  };
  useEffect(refresh, [projectId]);

  const regenerate = async (blockId: string) => {
    if (!projectId) return;
    setRegenerating(blockId);
    setError(null);
    try {
      await api.regenerateNarrationBlock(projectId, blockId);
      refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setRegenerating(null);
    }
  };

  return (
    <div>
      <h1>Voice Studio</h1>
      <p className="subtitle">ElevenLabs narration with real with-timestamps sync, or a clearly-labeled local placeholder when no API key is configured.</p>

      <div className="panel">
        <h2 style={{ marginTop: 0 }}>Provider Status</h2>
        <p className="requirement">
          ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID are read from the backend environment.
          Without them, every narration block is rendered by the local fallback
          synthesizer (an audible placeholder tone, not real speech) and tagged
          <code> is_placeholder_voice: true</code>. Configure the keys in Settings
          (.env) to use real ElevenLabs output.
        </p>
      </div>

      {!projectId && <div className="requirement">No project selected.</div>}
      {error && <div className="error-box">{error}</div>}

      {timeline && (
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>Narration Blocks</h2>
          <p className="subtitle">
            Regenerating one block re-synthesizes only that block's audio, then automatically
            retimes every later beat/caption/SFX cue if the new duration no longer fits --
            never a full re-render.
          </p>
          <table>
            <thead><tr><th>#</th><th>Text</th><th>Start</th><th>Provider</th><th>Placeholder?</th><th></th></tr></thead>
            <tbody>
              {timeline.narration.map((n: any, i: number) => (
                <tr key={n.id}>
                  <td>{i + 1}</td>
                  <td>{n.text}</td>
                  <td>{n.output_start_sec.toFixed(1)}s</td>
                  <td>{n.provider}</td>
                  <td>{n.is_placeholder_voice ? <span className="badge warn">placeholder</span> : <span className="badge ok">real</span>}</td>
                  <td>
                    <button className="secondary" disabled={regenerating === n.id} onClick={() => regenerate(n.id)}>
                      {regenerating === n.id ? "..." : "Regenerate"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
