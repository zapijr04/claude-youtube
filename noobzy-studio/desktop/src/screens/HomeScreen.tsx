import { useEffect, useState } from "react";
import { api, Project } from "../lib/api";
import { ScreenProps } from "../App";

export default function HomeScreen({ setProjectId, navigate }: ScreenProps) {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("New Roblox Challenge Video");
  const [preset, setPreset] = useState<Project["preset"]>("LONG_FORM_STORY");
  const [duration, setDuration] = useState(420);

  const refresh = () => {
    api.listProjects().then(setProjects).catch((e) => setError(String(e)));
  };

  useEffect(refresh, []);

  const create = async () => {
    setError(null);
    try {
      const p = await api.createProject({ name, preset, target_duration_sec: duration });
      refresh();
      setProjectId(p.id);
      navigate("import");
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div>
      <h1>Projects</h1>
      <p className="subtitle">Choose Long Video or Shorts, then import gameplay to start a project.</p>

      {error && <div className="error-box">Backend unreachable or errored: {error}. Is the API running (uvicorn app.main:app --port 8077)?</div>}

      <div className="panel">
        <h2 style={{ marginTop: 0 }}>New Project</h2>
        <div className="grid-2">
          <div>
            <label>Name<br /><input type="text" value={name} onChange={(e) => setName(e.target.value)} style={{ width: "100%" }} /></label>
          </div>
          <div>
            <label>Preset<br />
              <select value={preset} onChange={(e) => setPreset(e.target.value as Project["preset"])}>
                <option value="LONG_FORM_STORY">Long Video (16:9)</option>
                <option value="SHORT_EGG_REVEAL">Short (9:16)</option>
              </select>
            </label>
          </div>
        </div>
        <div style={{ marginTop: 10 }}>
          <label>Target duration (sec)<br />
            <input type="number" value={duration} onChange={(e) => setDuration(Number(e.target.value))} />
          </label>
        </div>
        <div style={{ marginTop: 14 }}>
          <button onClick={create}>Create Project &amp; Import Gameplay</button>
        </div>
      </div>

      <h2>Existing Projects</h2>
      {!projects && !error && <div className="requirement">Loading...</div>}
      {projects && projects.length === 0 && <div className="requirement">No projects yet -- create one above.</div>}
      {projects && projects.length > 0 && (
        <table>
          <thead><tr><th>Name</th><th>Preset</th><th>Status</th><th>Created</th><th></th></tr></thead>
          <tbody>
            {projects.map((p) => (
              <tr key={p.id}>
                <td>{p.name}</td>
                <td>{p.preset}</td>
                <td><span className="badge">{p.status}</span></td>
                <td>{new Date(p.created_at).toLocaleString()}</td>
                <td>
                  <button className="secondary" onClick={() => { setProjectId(p.id); navigate("import"); }}>Open</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
