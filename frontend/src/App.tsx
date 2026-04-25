import { Link, Route, Routes } from "react-router-dom";
import GalleryPage from "./pages/GalleryPage";
import DetailPage from "./pages/DetailPage";
import { exitApp } from "./api";

export default function App() {
  const onExit = async () => {
    try {
      await exitApp();
      window.alert("アプリを終了します。このブラウザタブは閉じてかまいません。");
    } catch (e) {
      window.alert(`終了に失敗しました: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-4 py-3 flex items-center justify-between gap-4">
          <Link to="/" className="text-lg font-semibold tracking-tight">
            Roly-Poly Toy Generator
          </Link>
          <button
            type="button"
            onClick={() => {
              void onExit();
            }}
            className="inline-flex items-center rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            終了
          </button>
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
