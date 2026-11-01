import { useEffect, useState } from "react";
import { api } from "../api";

let cached: string | null = null;

/** Small "v0.4.6" label so you can see which build you are testing. Tap it for the build id. */
export default function VersionBadge({ className = "" }: { className?: string }) {
  const [v, setV] = useState<string | null>(cached);
  const [build, setBuild] = useState("");
  useEffect(() => {
    api<{ version: string; build: string }>("/health")
      .then((h) => { cached = `v${h.version}`; setV(cached); setBuild(h.build); })
      .catch(() => undefined);
  }, []);
  if (!v) return null;
  return <span className={`version ${className}`} title={build ? `build ${build}` : undefined}>{v}</span>;
}
