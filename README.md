# roly-poly-toy-generator

A generator and curated gallery of physically stable, self-righting 3D models.

## 構成

- `backend/` — Python + FastAPI。gene の生成、metrics 計算、ローカル SQLite への保存、ビルド済みフロント配信を担当。
- `frontend/` — Vite + React + TypeScript + Tailwind v4 + react-three-fiber。一覧 (SVG サムネ) と 詳細 (3D ビュー) を提供。
- `data/` — ローカル実行時の SQLite DB と生成キャッシュ（git 管理外）。

## 必要なツール

- Python 3.11+（`uv` が自動で用意する構成）
- Node.js 20+ / npm
- `uv`（`python -m pip install uv` で導入可）

## セットアップ

```powershell
# バックエンド依存（uv が .venv を作る）
python -m uv sync

# フロントエンド依存
npm install
npm --prefix frontend install
```

## ローカルデータ

外部サービスは使わない。DB は起動時に `data/app.db` として自動作成される。
zip 配布版では **exe の隣の `data/`** に保存されるため、書き込み可能な場所に展開して実行する。

## 起動

ルートで以下を実行するとバックエンド（`:8000`）とフロントエンド（`:5173`）が同時に立ち上がる。

```powershell
npm run dev
```

ブラウザで `http://localhost:5173/` を開く。

- 「Generate 12 more」ボタンで 12 個ランダム生成される。
- 各サムネ（両側ミラー断面 + 重心マーカー）をクリックすると詳細ページに遷移し、3D モデルをマウスで操作できる。
- v2 以降の gene は「球キャップ底 + 5 次多項式テーパ」のパラメトリック族から生成し、傾き 75° までで自己復元可能な形状のみを採用する（`backend/app/physics.py` で feasibility 判定）。

## テスト

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```

`tests/test_physics.py` で球 / 円柱 / 円錐などの既知形状に対する feasibility 判定を、`tests/test_gene_generation.py` で大量サンプル時の全件合格と seed 再現性を確認している。

### 停止・トラブルシュート

開発時の終了はターミナルで `Ctrl+C`。`npm run dev` はオーケストレータが `SIGINT` を拾って backend / frontend のプロセスツリーを `taskkill /T /F` で落とすので、`uvicorn --reload` の子プロセスまでまとめて終了する。

ターミナルを強制終了して `:8000` や `:5173` を握ったままの孤児が残った場合は、次で回収できる。

```powershell
npm run stop
```

## API

| Method | Path                                    | 用途                          |
| ------ | --------------------------------------- | ----------------------------- |
| POST   | `/api/designs/generate`                 | N 個のデザインを生成          |
| GET    | `/api/designs?limit=..&offset=..`       | 一覧（新しい順）              |
| GET    | `/api/designs/{id}`                     | 詳細（gene + metrics）        |
| DELETE | `/api/designs`                          | 全デザイン一括削除            |
| POST   | `/api/app/exit`                         | ローカル配布版の終了          |

OpenAPI は `http://localhost:8000/docs` で参照可能。

## Windows zip 配布

Windows 向けの配布物は、ビルド済みフロント (`frontend/dist`) をフォルダとして同梱し、PyInstaller で作った exe からローカル FastAPI を起動する。

```powershell
npm run package:windows
```

生成物:

- `build/release/roly-poly-toy-generator-windows.zip`
- zip 内の `roly-poly-toy-generator/roly-poly-toy-generator.exe`
- zip 内の `roly-poly-toy-generator/frontend/dist/`
- zip 内の `roly-poly-toy-generator/data/`

利用者は zip を書き込み可能な場所（例: Desktop や Documents 配下）に展開し、`roly-poly-toy-generator.exe` をダブルクリックする。

配布版の挙動:

- 起動時に空きポートを自動選択し、既定ブラウザで `http://127.0.0.1:<port>/` を開く。
- Web UI 右上の **終了** ボタンでローカルサーバを停止する。
- ブラウザを閉じたまま放置した場合も、10分アクセスが無ければ自動停止する。
- SQLite DB は exe の隣の `data/app.db` に保存される。

### 配布版スモークテスト

1. `npm run package:windows` が成功し、zip が生成される。
2. zip を別フォルダに展開し、`roly-poly-toy-generator.exe` をダブルクリックする。
3. ブラウザが自動で開き、ギャラリーが表示される。
4. 「12個追加生成」でデザインが作成され、一覧・詳細・STL出力が動く。
5. UI右上の「終了」をクリックすると、exeプロセスが終了する。
6. 再起動後も前回のデザインが `data/app.db` から復元される。
7. ブラウザを閉じて10分放置した場合、exeプロセスが自動終了する。

---

## 実装概要

### 設計原則

1. **再現性とID** — 同じ形状には同じ ID を与える。gene を正規化 JSON（キー順固定、float 小数第4位丸め）にシリアライズし、SHA-256 の先頭 16 hex 文字を `design_id` とする（`backend/app/identify.py`）。ID だけで形状を完全に再現できる。
2. **回転対称（鉛直軸）** — モデルは Z 軸に対して回転対称。生成・評価の対象は断面片側の半径関数 `r(z)` であり、「2D 断面 → 回転体として 3D 化」が基本パイプライン。
3. **永続化はローカル SQLite** — メタデータ（gene / metrics / feasibility / created_at）は `data/app.db` に保存。派生アセット（SVG サムネ / 3D メッシュ / STL / STEP）は DB に置かず、フロントエンドが gene からオンデマンド生成する。Backend はアセット配信をしない。
4. **プロトタイプ最速完成 > きれいな設計 > 高機能化** — 不確実な設計検討より動く最小構成を優先する。
5. **ローカル完結** — 認証・マルチテナント・外部サービスは非対象。単一ユーザーのローカルアプリとして運用する。

### 遺伝子（gene）仕様

- スキーマバージョン: `GENE_VERSION = 2`
- 区分線形の半径関数 `r(z)`。制御点数 `N = 64`、z 軸上の配置は `z_i = height · (i/(N-1))²`（z_warp=2.0; z=0 付近にノードを密集させ球キャップの √z 型特異点を忠実に再現）。
- 形状制約（単峰）: ある `k` まで `r_i < r_{i+1}`、`k` 以降 `r_i > r_{i+1}`。
- 両端: `r_0 = 0`（球キャップの極点）、`r_{N-1} = rt`（上端。`rt=0` も可）。
- 生成は「球キャップ底 + 5 次多項式テーパ」のパラメトリック族から `(rb, cap_angle, rt, delta_target)` をランダムに引き、高さを delta = rb - z_com が狙い値になるよう最適化（細長さ・成立性・δ目標を同時評価）で調整したあと、制御点に微小な radial jitter を乗せて個体差を出す。
- **物理制約**: θ_max = 75° まで自己復元することを保証。各接地点での「CoG が曲率中心より下」条件を r' ≥ cot(75°) の区間で満たす gene だけを採用（`backend/app/physics.py`）。

### 評価指標（Metrics）

- `volume`（円錐台の総和）、`height`、`max_width`（= 2 × max(r)）、`centroid_z`（一様密度仮定、体積加重）
- `z_cog_suggested`: θ_max=75° で復元するための推奨 CoG 高さ（safety_margin 込み）
- `z_cog_max`: 自己復元できる z_CoG の上限
- `bottom_curvature_radius`: 南極近傍の有効子午面曲率半径

### アセット生成（フロントエンド側）

すべて `frontend/src/derive/` 内で gene からクライアントサイド生成する。Backend には派生アセット生成を置かない。

- **サムネイル** (`thumbnailSvg.ts`): SVG。両側ミラーした実断面 + 重心の赤十字マーカー + z_cog_max の青十字マーカー。
- **3D 表示** (`mesh.ts`): カスタム `revolveWatertightGeometry` で watertight な回転体メッシュを生成し、react-three-fiber でブラウザ上に表示。
- **STL / STEP** (`stlExporter.ts` / `stepExporter.ts`): three.js の `STLExporter` や opencascade.js によりブラウザ上で生成しダウンロード。

### 生成・保存

- 1 バッチ = 12 個（`BATCH_SIZE = 12`）。
- 全生成物を保存（選抜なし）。派生アセットは保存しない。
- すべて同期処理（リクエスト中に生成完了まで待つ）。ジョブ/キューは未導入。
- 親デザインを最大4つ選択して次世代を生成する交叉機能あり（`breed_gene_with_feasibility`）。

### UI

- **一覧 (Gallery)**: 断面 SVG サムネをグリッド表示。デザインを最大 4 つ選択して「選択から 12 個生成」が可能。一括削除機能あり。
- **詳細 (Detail)**: 3D モデルの回転・拡大縮小操作、断面 SVG、metrics パネル、STL/STEP ダウンロード。

### 技術スタック

| 層 | 技術 |
|---|---|
| Backend | Python 3.11+ / FastAPI / SQLite (WAL) / NumPy |
| Frontend | Vite 5 / React 18 / TypeScript / Tailwind CSS v4 |
| 3D | three.js 0.169 / react-three-fiber / @react-three/drei |
| 型生成 | openapi-typescript（Backend の OpenAPI スキーマからフロント型を自動生成） |
| 配布 | PyInstaller（exe 化）+ ビルド済み frontend/dist 同梱 |

### 迷ったときの判断基準

- **この変更はプロトタイプ完成を早めるか？** → Yes なら優先
- **ローカル完結で十分か？** → Yes なら外部配信前提の設計は不要
- **IDで再現できるか？** → No なら設計を見直す
- **回転対称（断面片側）を壊していないか？** → 壊すなら要相談

### 未着手（Deferred）

- 体積など、個体差を抑えるための追加制約
- 印刷性などの評価指標、重り配置の自動最適化
- 比較 UI、フィルタ、タグ、お気に入り
- `manifold3d` 等への移行と高品質メッシュ化

---

## フォルダ構成

```
roly-poly-toy-generator/
├── backend/
│   ├── __init__.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── api.py              # FastAPI ルータ（generate / list / detail / delete）
│   │   ├── config.py           # 全定数の集約（形状パラメータ値域・パス・バッチサイズ等）
│   │   ├── gene.py             # gene のランダム生成・交叉（v2: 球キャップ+5次テーパ）
│   │   ├── identify.py         # gene → design_id（正規化 JSON → SHA-256 先頭16 hex）
│   │   ├── launcher.py         # 配布版 exe のエントリポイント（ポート自動選択・ブラウザ起動）
│   │   ├── main.py             # FastAPI アプリ生成（CORS・静的配信・アイドル自動停止）
│   │   ├── metrics.py          # volume / height / max_width / centroid_z の算出
│   │   ├── models.py           # Pydantic モデル（Gene / Metrics / DesignSummary 等）
│   │   ├── physics.py          # 起き上がりこぼし物理判定（feasibility / 曲率半径）
│   │   ├── shape.py            # パラメトリック形状族（球キャップ+5次テーパ）と高さ最適化
│   │   ├── smoothing.py        # gene の radii → 密プロファイル補間
│   │   └── storage.py          # SQLite CRUD（designs テーブル）
│   └── scripts/
│       └── export_openapi.py   # OpenAPI スキーマ JSON 出力
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── scripts/
│   │   └── fetch-openapi.mjs   # バックエンドから openapi.json を取得
│   └── src/
│       ├── App.tsx              # ルーティング（Gallery / Detail）
│       ├── api.ts               # Backend HTTP クライアント
│       ├── index.css
│       ├── main.tsx             # React エントリポイント
│       ├── types.ts             # OpenAPI 生成型の再 export
│       ├── components/
│       │   ├── DesignCard.tsx   # 一覧カード（SVG サムネ + metrics）
│       │   ├── MetricsPanel.tsx # 詳細画面の指標パネル
│       │   └── ModelViewer.tsx  # 3D ビューア（react-three-fiber + OrbitControls）
│       ├── derive/
│       │   ├── mesh.ts          # gene → watertight 回転体メッシュ（three.js）
│       │   ├── mesh.test.ts
│       │   ├── smoothing.ts     # gene の radii → 密プロファイル補間（TS 版）
│       │   ├── smoothing.test.ts
│       │   ├── stepExporter.ts  # gene → STEP Blob（opencascade.js）
│       │   ├── stlExporter.ts   # メッシュ → STL Blob（three.js STLExporter）
│       │   └── thumbnailSvg.ts  # gene → 断面 SVG（両側ミラー + 重心マーカー）
│       ├── generated/
│       │   ├── openapi.json     # Backend から取得した OpenAPI スキーマ
│       │   └── api-schema.ts    # openapi-typescript で生成した型定義
│       └── pages/
│           ├── GalleryPage.tsx  # 一覧ページ（生成・選択・削除）
│           └── DetailPage.tsx   # 詳細ページ（3D・断面・STL出力）
├── tests/
│   ├── conftest.py
│   ├── test_api.py              # API エンドポイントの統合テスト
│   ├── test_gene_generation.py  # 大量サンプル全件合格・seed 再現性テスト
│   ├── test_identify.py         # design_id の決定性・正規化テスト
│   ├── test_metrics.py          # metrics 算出のテスト
│   ├── test_physics.py          # 既知形状（球・円柱・円錐）の feasibility テスト
│   └── test_storage.py          # SQLite CRUD のテスト
├── scripts/
│   ├── dev.mjs                  # npm run dev のオーケストレータ
│   ├── stop.mjs                 # 孤児プロセス回収
│   └── package-windows.ps1     # Windows zip 配布ビルド
├── data/
│   └── app.db                   # ローカル SQLite DB（git 管理外）
├── build/                       # PyInstaller 出力・配布 zip（git 管理外）
├── MATH_ROLY_POLY_TOY.md       # 起き上がりこぼしの数学的背景
├── pyproject.toml               # Python プロジェクト定義（uv 用）
├── package.json                 # ルートの npm scripts（dev / stop / package:windows）
└── roly-poly-toy-generator.spec # PyInstaller 設定
```
