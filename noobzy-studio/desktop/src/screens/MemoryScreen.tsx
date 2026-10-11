import { useState } from "react";
import { api } from "../lib/api";
import { ScreenProps } from "../App";

export default function MemoryScreen({ projectId }: ScreenProps) {
  const [text, setText] = useState("give me more suspense before the reveal");
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const send = async () => {
    setError(null);
    try {
      const r = await api.creativeBrief(text, projectId ?? undefined);
      setResult(r);
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div>
      <h1>Memory &amp; Creative Brief</h1>
      <p className="subtitle">Type a short instruction; it's parsed into a typed, editable plan-change proposal with recorded provenance -- never silently applied.</p>
      {error && <div className="error-box">{error}</div>}

      <div className="panel">
        <input type="text" style={{ width: "100%" }} value={text} onChange={(e) => setText(e.target.value)} />
        <div style={{ marginTop: 10 }}>
          <button onClick={send}>Parse Intent</button>
        </div>
      </div>

      {result && (
        <div className="panel">
          <h2 style={{ marginTop: 0 }}>Parsed Action</h2>
          <pre style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>{JSON.stringify(result.action, null, 2)}</pre>
          {result.action.action === "unrecognized" && (
            <p className="requirement">No rule matched -- this is a small deterministic matcher, not full language understanding. The brief was still recorded for later review.</p>
          )}
        </div>
      )}
    </div>
  );
}
