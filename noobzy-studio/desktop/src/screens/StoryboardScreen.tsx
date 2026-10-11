import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { ScreenProps } from "../App";

export default function StoryboardScreen({ projectId }: ScreenProps) {
  const [timeline, setTimeline] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    api.getTimeline(projectId).then(setTimeline).catch((e) => setError(String(e)));
  }, [projectId]);

  if (!projectId) return <div><h1>Storyboard / Script</h1><div className="requirement">No project selected.</div></div>;
  if (error) return <div><h1>Storyboard / Script</h1><div className="requirement">No timeline yet -- run Import &amp; Analyze first.</div></div>;
  if (!timeline) return <div><h1>Storyboard / Script</h1><p className="subtitle">Loading...</p></div>;

  return (
    <div>
      <h1>Storyboard / Script</h1>
      <p className="subtitle">Every beat below cites its source timestamp -- nothing here is invented without evidence.</p>
      {timeline.beats.map((beat: any, i: number) => {
        const narration = timeline.narration[i];
        return (
          <div className="panel" key={beat.id}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <strong>{beat.kind.toUpperCase()}</strong>
              <span className="badge">{beat.output_start_sec.toFixed(1)}s - {beat.output_end_sec.toFixed(1)}s</span>
            </div>
            <p className="subtitle" style={{ margin: "6px 0" }}>{beat.summary}</p>
            {narration && <p style={{ fontSize: 13 }}>&ldquo;{narration.text}&rdquo;</p>}
          </div>
        );
      })}
    </div>
  );
}
