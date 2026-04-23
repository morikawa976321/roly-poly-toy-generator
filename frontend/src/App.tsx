import { Link, Route, Routes } from "react-router-dom";
import GalleryPage from "./pages/GalleryPage";
import DetailPage from "./pages/DetailPage";
import { SMOOTHING_OPTIONS, useSmoothing } from "./smoothing";
import type { SmoothingMethod } from "./smoothing";

function SmoothingPicker() {
  const { smoothing, setSmoothing } = useSmoothing();
  const current = SMOOTHING_OPTIONS.find((o) => o.value === smoothing);
  return (
    <div className="flex items-center gap-2">
      <label className="text-xs text-slate-500" htmlFor="smoothing-select">
        curve
      </label>
      <select
        id="smoothing-select"
        value={smoothing}
        onChange={(e) => setSmoothing(e.target.value as SmoothingMethod)}
        className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-800 hover:border-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-400"
        title={current?.description ?? ""}
      >
        {SMOOTHING_OPTIONS.map((o) => (
          <option key={o.value} value={o.value} title={o.description}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-4 py-3 flex items-center justify-between gap-4">
          <Link to="/" className="text-lg font-semibold tracking-tight">
            Roly-Poly Toy Generator
          </Link>
          <div className="flex items-center gap-4">
            <SmoothingPicker />
            <span className="text-xs text-slate-500">local pre-prototype</span>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Routes>
          <Route path="/" element={<GalleryPage />} />
          <Route path="/designs/:id" element={<DetailPage />} />
        </Routes>
      </main>
    </div>
  );
}
