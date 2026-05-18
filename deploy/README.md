# Roly-Poly Design Viewer（Vercel デプロイ用）

デザイン `6d7afe17fed27c7c` 固定の単ページビューアです。  
メインアプリ（`frontend/` + `backend/`）とは独立しており、**この `deploy/` ディレクトリだけ**を Vercel の Root Directory に指定してデプロイします。

## 構成

- `src/App.tsx` … 詳細ページ相当の UI（保存・ギャラリーなし）
- `src/design.json` … 埋め込みデザインデータ（`docs/designs/.../dump.json` から生成）
- `@core` エイリアス … `../frontend/src` の derive / components / types を参照
- `src/derive/stepExporter.ts` … `frontend` から `npm run sync-core` で同期（STEP 出力。`dev` / `build` 前に自動実行）

バックエンドは不要です（静的ホスティングのみ）。

## メッシュ / STEP の形状パイプライン

メインアプリ・backend の `effective_profile` と同じ順序です（`@core/derive` 経由）。

1. **ガウシアン平滑** … `smoothProfile`（64 制御点 → 密 z 格子 + σ=24）
2. **上部延長** … 接続条件はガウシアン母線、5 次外挿（`legacyMeshProfile`）
3. **B3 再フィット** … 上記密 (z,r) を同じ z で `UnivariateSpline`（Pyodide + SciPy）
4. **カット** … 回転メッシュ生成後に平面クリップ（`clipGeneMesh`）。STEP も同様

初回表示時にブラウザが Pyodide（numpy/scipy）を CDN から読み込みます。

## ローカル開発

```bash
cd deploy
npm install
npm --prefix ../frontend install   # @core が参照する frontend の型・依存
npm run dev
```

## Vercel

1. 新規プロジェクトを作成
2. **Root Directory**: `deploy`
3. Framework Preset: Vite（`vercel.json` あり）
4. デプロイ

`@core` は `../frontend/src` を参照するため、ビルド時に `frontend` の `npm ci` も実行します（`vercel.json` の `installCommand`）。

## デザインデータの更新

`docs/designs/6d7afe17fed27c7c/dump.json` を更新したあと:

```bash
cd deploy
npm run sync-design
```

STEP エクスポートのロジックを `frontend` 側で直したあとは、再デプロイ前に `npm run sync-core`（または `npm run build`）を実行してください。`dev` / `build` では自動同期されます。

## 削除

デプロイが不要になったら **`deploy/` ディレクトリを削除**するだけで、メインアプリには影響しません。
