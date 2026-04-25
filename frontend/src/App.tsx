import { Link, Route, Routes } from "react-router-dom";
import GalleryPage from "./pages/GalleryPage";
import DetailPage from "./pages/DetailPage";

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-4 py-3 flex items-center justify-between gap-4">
          <Link to="/" className="text-lg font-semibold tracking-tight">
            Roly-Poly Toy Generator
          </Link>
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
