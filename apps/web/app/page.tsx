import Demo from "./demo";

export default function Page() {
  return (
    <main>
      <p className="eyebrow">TIER A · SYNTHETIC DATA ONLY</p>
      <h1>Academic Navigator</h1>
      <p className="lede">
        This local slice demonstrates subject isolation and deterministic uncertainty.
        It does not use or validate Waterloo data.
      </p>
      <Demo />
    </main>
  );
}

