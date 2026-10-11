import { useEffect, useRef, useState } from "react";
import { api, SkillManifest } from "../lib/api";
import { ScreenProps } from "../App";

export default function SkillsLabScreen(_: ScreenProps) {
  const [skills, setSkills] = useState<SkillManifest[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = () => {
    api.listSkills().then(setSkills).catch((e) => setError(String(e)));
  };
  useEffect(() => {
    refresh();
  }, []);

  const approve = async (id: string) => {
    await api.approveSkill(id);
    refresh();
  };

  const importFile = async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${(window as any).NOOBZY_API_BASE ?? "http://127.0.0.1:8077"}/skills/import`, { method: "POST", body: form });
    if (!res.ok) {
      setError(await res.text());
      return;
    }
    refresh();
  };

  return (
    <div>
      <h1>Skills Lab</h1>
      <p className="subtitle">Built-in and user-imported versioned skills. A new skill is staged disabled until approved.</p>
      {error && <div className="error-box">{error}</div>}

      <div className="panel">
        <h2 style={{ marginTop: 0 }}>Import a Skill (Markdown)</h2>
        <input ref={fileRef} type="file" accept=".md" onChange={(e) => e.target.files?.[0] && importFile(e.target.files[0])} />
      </div>

      {!skills && <p className="subtitle">Loading...</p>}
      {skills && (
        <table>
          <thead><tr><th>ID</th><th>Title</th><th>Provenance</th><th>Enabled</th><th></th></tr></thead>
          <tbody>
            {skills.map((s) => (
              <tr key={s.id}>
                <td style={{ fontFamily: "monospace", fontSize: 11 }}>{s.id}</td>
                <td>{s.title}</td>
                <td><span className="badge">{s.provenance}</span></td>
                <td>{s.enabled ? <span className="badge ok">enabled</span> : <span className="badge off">disabled</span>}</td>
                <td>{!s.enabled && <button className="secondary" onClick={() => approve(s.id)}>Approve</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
