import { useEffect, useState } from "react";
import { api, ComputeProviderStatus } from "../lib/api";
import { ScreenProps } from "../App";

export default function ComputeScreen(_: ScreenProps) {
  const [providers, setProviders] = useState<ComputeProviderStatus[] | null>(null);

  useEffect(() => {
    api.computeProviders().then(setProviders).catch(() => setProviders(null));
  }, []);

  return (
    <div>
      <h1>Compute / GPU</h1>
      <p className="subtitle">
        Local CPU editing always works. GPU/cloud providers are detected, not assumed --
        this is not a "free supercomputer". No paid job submits without an explicit cost
        approval and a spending cap.
      </p>
      {!providers && <p className="subtitle">Loading...</p>}
      {providers && (
        <table>
          <thead><tr><th>Provider</th><th>Status</th><th>Detail</th></tr></thead>
          <tbody>
            {providers.map((p) => {
              const ok = (p as any).available === true || (p as any).status === "available" || (p as any).reachable === true;
              const { provider, ...rest } = p;
              return (
                <tr key={provider}>
                  <td>{provider}</td>
                  <td>{ok ? <span className="badge ok">available</span> : <span className="badge off">not configured</span>}</td>
                  <td style={{ fontFamily: "monospace", fontSize: 11 }}>{JSON.stringify(rest)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
