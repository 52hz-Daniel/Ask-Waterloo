"use client";

import { useState } from "react";

type Result = {
  assessment: "SATISFIED" | "NOT_SATISFIED" | "UNKNOWN";
  registration: "NOT_EVALUATED";
  findings: { code: string; state: string; rule_path: string }[];
  limitations: string[];
  snapshot_bundle: string;
};

export default function Demo() {
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function assess() {
    setError(null);
    const response = await fetch("/api/assessment", { method: "POST" });
    if (!response.ok) {
      setError("The synthetic assessment could not be completed.");
      return;
    }
    setResult((await response.json()) as Result);
  }

  return (
    <section aria-labelledby="demo-heading">
      <h2 id="demo-heading">Synthetic assessment proof</h2>
      <p>SYN 300 contains one supported completion clause and one unsupported clause.</p>
      <button type="button" onClick={assess}>Assess synthetic profile</button>
      {error && <p role="alert">{error}</p>}
      {result && (
        <article aria-live="polite">
          <strong className={`badge ${result.assessment.toLowerCase()}`}>
            {result.assessment}
          </strong>
          <p>Registration: {result.registration}</p>
          <ul>{result.findings.map((f) => <li key={f.rule_path}>{f.code}: {f.state}</li>)}</ul>
          {result.limitations.map((item) => <p key={item}>{item}</p>)}
          <small>Fixture bundle: {result.snapshot_bundle}</small>
        </article>
      )}
    </section>
  );
}

