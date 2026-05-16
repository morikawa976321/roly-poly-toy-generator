# roly-poly-toy-generator

起き上がりこぼし（自己復元回転体）の生成・ギャラリー・3D プレビュー・STEP 出力を行うローカル Web アプリ。

## 構成

- `backend/` — Python + FastAPI。gene の生成・交叉、metrics 計算、SQLite 保存、ビルド済みフロント配信。
- `frontend/` — Vite + React + TypeScript + Tailwind v4 + react-three-fiber。ギャラリー（SVG サムネ）と詳細（3D・上部加工・STEP）。
- `deploy/` — 単一デザイン固定のスタティックビューア（Vercel 用。`deploy/README.md` 参照）。backend 不要。
- `docs/designs/` — リファレンスデザインの JSON ダンプ（検証・deploy 用）。
- `data/` — ローカル SQLite DB（`app.db`、git 管理外）。

## 必要なツール

- Python 3.11+（`uv` が `.venv` を用意）
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

OpenAPI 由来の TypeScript 型を再生成する場合（CI と同じ手順）:

```powershell
python backend/scripts/export_openapi.py frontend/src/generated/openapi.json
npm --prefix frontend run gen:types
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

- **12個追加生成** で 12 個ランダム生成。カードを最大 4 つ選択すると **選択（N）から12個生成** で交叉生成。
- サムネ（両側ミラー断面 + 重心・z_cog_max マーカー）をクリックすると詳細へ。3D はマウスで回転・ズーム可能。
- 詳細では **上部延長**（C² 5次外挿）と **斜めカット平面**（高さ・傾き）をスライダーでプレビューし、**保存** で SQLite に反映。STEP 出力はプレビュー中の形状に追従。
- v2 gene は「球キャップ底 + 5 次多項式テーパ」から生成し、傾き 75° まで自己復元可能な形状のみ採用（`backend/app/physics.py`）。

## テスト

```powershell
# Python（backend + 共有 derive ロジック）
.venv\Scripts\python.exe -m pytest tests/ -q

# TypeScript（frontend derive）
npm --prefix frontend test
```

主なカバレッジ: `test_physics.py`（既知形状の feasibility）、`test_gene_generation.py`（大量サンプル・seed 再現性）、`test_profile_extension.py` / `test_profile_cut.py`（延長・カット）、`test_feasibility_metrics.py`（カット後 z_cog_max）、frontend の `derive/*.test.ts`（メッシュ・STEP 周辺）。

### 停止・トラブルシュート

開発時の終了はターミナルで `Ctrl+C`。`npm run dev` はオーケストレータが `SIGINT` を拾って backend / frontend のプロセスツリーを `taskkill /T /F` で落とすので、`uvicorn --reload` の子プロセスまでまとめて終了する。

ターミナルを強制終了して `:8000` や `:5173` を握ったままの孤児が残った場合:

```powershell
npm run stop
```

## API

| Method | Path                              | 用途 |
| ------ | --------------------------------- | ---- |
| POST   | `/api/designs/generate`           | N 個生成（`parent_ids` で交叉可、最大 4 親） |
| GET    | `/api/designs?limit=..&offset=..` | 一覧（新しい順） |
| GET    | `/api/designs/{id}`               | 詳細（gene + metrics） |
| PATCH  | `/api/designs/{id}`               | `top_extension_mm` / `top_cut_height_mm` / `top_cut_angle_deg` 更新 |
| DELETE | `/api/designs`                    | 全デザイン一括削除 |
| POST   | `/api/app/exit`                   | ローカル配布版の終了 |

OpenAPI は `http://localhost:8000/docs` で参照可能。フロント型は `frontend/src/generated/` にコミットし、`.github/workflows/verify-generated-types.yml` でドリフトを検知する。

## Windows zip 配布

ビルド済みフロント (`frontend/dist`) を同梱し、PyInstaller の exe からローカル FastAPI を起動する。

```powershell
npm run package:windows
```

生成物:

- `build/release/roly-poly-toy-generator-windows.zip`
- zip 内の `roly-poly-toy-generator/roly-poly-toy-generator.exe`
- zip 内の `roly-poly-toy-generator/frontend/dist/`
- zip 内の `roly-poly-toy-generator/data/`

利用者は zip を書き込み可能な場所（Desktop / Documents 等）に展開し、`roly-poly-toy-generator.exe` をダブルクリックする。

配布版の挙動:

- 起動時に空きポートを自動選択し、既定ブラウザで `http://127.0.0.1:<port>/` を開く。
- Web UI 右上の **終了** でローカルサーバを停止。
- ブラウザを閉じたまま 10 分アクセスが無ければ自動停止。
- SQLite DB は exe 隣の `data/app.db` に保存（上部延長・カット設定も gene に含めて永続化）。

### 配布版スモークテスト

1. `npm run package:windows` が成功し、zip が生成される。
2. zip を別フォルダに展開し、`roly-poly-toy-generator.exe` をダブルクリックする。
3. ブラウザが自動で開き、ギャラリーが表示される。
4. 「12個追加生成」でデザインが作成され、一覧・詳細・STEP 出力が動く。
5. 詳細で上部延長・カットを変更し「保存」→ 再起動後も設定が復元される。
6. UI 右上の「終了」で exe プロセスが終了する。
7. ブラウザを閉じて 10 分放置すると exe が自動終了する。

---

## 実装概要

### 設計原則

1. **再現性と ID** — ベース形状（`radii` / `height` 等）を正規化 JSON（キー順固定、float 小数第 4 位丸め）→ SHA-256 先頭 16 hex が `design_id`（`backend/app/identify.py`）。`top_extension_mm` / `top_cut_*` は保存用パラメータで **ID には含めない**（同じベース形状に加工差分を載せる）。
2. **回転対称（鉛直軸）** — Z 軸回りの回転体。基本は断面片側 `r(z)` → 密プロファイル → 回転体メッシュ。
3. **永続化はローカル SQLite** — gene / metrics / `created_at` のみ DB 保存。SVG・3D・STEP はフロントが gene からオンデマンド生成（backend は配信しない）。
4. **プロトタイプ最速完成 > きれいな設計 > 高機能化**
5. **ローカル完結** — 認証・マルチテナント・外部 DB は非対象（`deploy/` の静的公開は任意）。

### 遺伝子（gene）仕様

- スキーマ: `GENE_VERSION = 2`
- 制御点 `N = 64`、`z_i = height · (i/(N-1))²`（`z_warp = 2.0`、球キャップ極の √z 特異点向け）
- 単峰: ある `k` まで単調増加、`k` 以降単調減少
- 両端: `r_0 = 0`（球キャップ極）、`r_{N-1} = rt`（上端、`rt = 0` 可）
- 生成: 球キャップ + 5 次テーパ族からサンプル → 高さ最適化 → radial jitter
- **物理制約**: θ_max = 75° まで自己復元（`backend/app/physics.py`）
- **加工パラメータ**（DB 保存・`design_id` 対象外）:
  - `top_extension_mm` — 上端からの C² 5 次延長（上限は上端が尖るまで、`profile_extension.py`）
  - `top_cut_height_mm` / `top_cut_angle_deg` — 斜め平面カット（0° = 水平、`profile_cut.py`）

### 評価指標（Metrics）

体積・高さ・最大幅・重心は **延長＋カット後の回転体メッシュ** から算出（backend `mesh_revolve` + `mesh_plane_cut`、frontend `mesh` + `meshPlaneCut` で整合）。

- `volume`, `height`, `max_width`, `centroid_z`
- `z_cog_max` — カット後子午線に対する自己復元 z_CoG 上限（0.85 安全率込み）
- `bottom_curvature_radius` — 南極近傍の有効曲率半径

### アセット生成（フロントエンド側）

`frontend/src/derive/` で gene からクライアント生成。backend は数値 metrics のみ（アセットなし）。

| モジュール | 役割 |
| --- | --- |
| `smoothing.ts` / `profileExtension.ts` | 密プロファイル・上部延長 |
| `meshPlaneCut.ts` | 子午面カット・3D 平面クリップ |
| `mesh.ts` / `meshMetrics.ts` | watertight 回転体・体積・断面 |
| `physics.ts` / `feasibilityMetrics.ts` | feasibility・z_cog_max 等 |
| `metrics.ts` | プレビュー用 metrics（保存前も即時計算） |
| `thumbnailSvg.ts` | 断面 SVG（ミラー + マーカー） |
| `stepExporter.ts` | STEP Blob（opencascade.js） |

### 生成・保存

- 1 バッチ = 12 個（`BATCH_SIZE = 12`）
- 全件保存（選抜なし）、派生アセットは保存しない
- 同期処理（ジョブキューなし）
- 親最大 4 つで交叉（`breed_gene_with_feasibility`）
- 詳細の加工は `PATCH /api/designs/{id}` で gene を更新し metrics を再計算

### UI

- **一覧 (Gallery)**: SVG グリッド、選択（最大 4）→ 交叉生成、一括削除
- **詳細 (Detail)**: 3D ビュー、上部延長・カットのライブプレビュー（400ms デバウンス）、保存、断面 SVG、metrics、STEP ダウンロード

### 技術スタック

| 層 | 技術 |
| --- | --- |
| Backend | Python 3.11+ / FastAPI / SQLite (WAL) / NumPy |
| Frontend | Vite 5 / React 18 / TypeScript / Tailwind CSS v4 / Vitest |
| 3D | three.js 0.169 / react-three-fiber / @react-three/drei |
| CAD 出力 | opencascade.js（ブラウザ内 STEP 生成） |
| 型生成 | openapi-typescript + CI で `generated/` のドリフト検知 |
| 配布 | PyInstaller + `frontend/dist` 同梱 |
| 公開（任意） | `deploy/` → Vercel 静的ホスティング |

### 迷ったときの判断基準

- **この変更はプロトタイプ完成を早めるか？** → Yes なら優先
- **ローカル完結で十分か？** → Yes なら外部配信前提の設計は不要
- **ベース形状の ID で再現できるか？** → 加工パラメータは ID 外。ベース gene が変わるなら要相談
- **回転対称（断面片側）を壊していないか？** → 壊すなら要相談
- **backend / frontend の metrics・カット結果は一致するか？** → ズレるなら derive を両方直す

### 未着手（Deferred）

- 体積など、個体差を抑えるための追加制約
- 印刷性などの評価指標、重り配置の自動最適化
- 比較 UI、フィルタ、タグ、お気に入り
- `manifold3d` 等への移行と高品質メッシュ化

---

## フォルダ構成

```
roly-poly-toy-generator/
├── .github/
│   └── workflows/
│       └── verify-generated-types.yml  # OpenAPI 型生成の CI 検証
├── backend/
│   ├── __init__.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── api.py                  # FastAPI ルータ（generate / list / detail / delete）
│   │   ├── config.py               # 全定数の集約（形状パラメータ値域・パス・バッチサイズ等）
│   │   ├── feasibility_metrics.py  # カット後 z_cog_max / bottom_curvature_radius 算出
│   │   ├── gene.py                 # gene のランダム生成・交叉（v2: 球キャップ+5次テーパ）
│   │   ├── identify.py             # gene → design_id（正規化 JSON → SHA-256 先頭16 hex）
│   │   ├── launcher.py             # 配布版 exe のエントリポイント（ポート自動選択・ブラウザ起動）
│   │   ├── main.py                 # FastAPI アプリ生成（CORS・静的配信・アイドル自動停止）
│   │   ├── mesh_plane_cut.py       # 回転体メッシュの 3D 平面カット（TS meshPlaneCut 相当）
│   │   ├── mesh_revolve.py         # (z, r) プロファイル → 回転体三角メッシュ
│   │   ├── metrics.py              # volume / height / max_width / centroid_z の算出
│   │   ├── models.py               # Pydantic モデル（Gene / Metrics / DesignSummary 等）
│   │   ├── physics.py              # 起き上がりこぼし物理判定（feasibility / 曲率半径）
│   │   ├── profile_cut.py          # 子午面プロファイルへの傾斜カット
│   │   ├── profile_extension.py    # 上部延長（C² 5次外挿）と feasibility 用プロファイル
│   │   ├── shape.py                # パラメトリック形状族（球キャップ+5次テーパ）と高さ最適化
│   │   ├── smoothing.py            # gene の radii → 密プロファイル補間
│   │   └── storage.py              # SQLite CRUD（designs テーブル）
│   └── scripts/
│       └── export_openapi.py       # OpenAPI スキーマ JSON 出力
├── deploy/                         # Vercel 用スタティックビューア（backend 不要）
│   ├── README.md
│   ├── index.html
│   ├── package.json
│   ├── vercel.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── scripts/
│   │   ├── sync-design.mjs       # docs/designs/.../dump.json → src/design.json
│   │   └── sync-core-derive.mjs  # frontend derive を @core 向けに同期
│   └── src/
│       ├── App.tsx                 # 単一デザイン詳細 UI（ギャラリー・保存なし）
│       ├── main.tsx
│       ├── index.css
│       ├── design.json             # 埋め込みデザインデータ
│       └── derive/
│           ├── stepExporter.ts     # STEP 出力（frontend から sync-core で同期）
│           └── stepProfile.ts      # STEP 用プロファイル間引き・B-spline エッジ
├── docs/
│   └── designs/
│       └── 6d7afe17fed27c7c/       # リファレンスデザインの完全ダンプ（検証・deploy 用）
│           ├── README.md
│           ├── gene.json
│           ├── dump.json
│           ├── smooth_profile.json
│           ├── smooth_profile_z_mm.json
│           ├── smooth_profile_r_mm.json
│           └── z_nodes_mm.json
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── scripts/
│   │   └── fetch-openapi.mjs       # バックエンドから openapi.json を取得
│   └── src/
│       ├── App.tsx                 # ルーティング（Gallery / Detail）
│       ├── api.ts                  # Backend HTTP クライアント
│       ├── index.css
│       ├── main.tsx                # React エントリポイント
│       ├── types.ts                # OpenAPI 生成型の再 export
│       ├── components/
│       │   ├── DesignCard.tsx      # 一覧カード（SVG サムネ + metrics）
│       │   ├── MetricsPanel.tsx    # 詳細画面の指標パネル
│       │   └── ModelViewer.tsx     # 3D ビューア（react-three-fiber + OrbitControls）
│       ├── derive/
│       │   ├── mesh.ts             # gene → watertight 回転体メッシュ（three.js）
│       │   ├── mesh.test.ts
│       │   ├── meshMetrics.ts      # メッシュからの断面・体積・重心算出
│       │   ├── meshPlaneCut.ts     # 子午面カット・3D 平面クリップ
│       │   ├── smoothing.ts        # gene の radii → 密プロファイル補間（TS 版）
│       │   ├── smoothing.test.ts
│       │   ├── profileExtension.ts # 上部延長（C² 5次外挿）
│       │   ├── physics.ts          # プロファイルからの feasibility 判定
│       │   ├── metrics.ts          # プロファイルからの体積・高さ等
│       │   ├── metrics.test.ts
│       │   ├── feasibilityMetrics.ts   # カット後 z_cog_max 等（gene 一括算出）
│       │   ├── feasibilityMetrics.test.ts
│       │   ├── stepExporter.ts     # gene → STEP Blob（opencascade.js）
│       │   ├── thumbnailSvg.ts   # gene → 断面 SVG（両側ミラー + 重心マーカー）
│       │   └── thumbnailSvg.test.ts
│       ├── generated/
│       │   ├── openapi.json        # Backend から取得した OpenAPI スキーマ
│       │   └── api-schema.ts       # openapi-typescript で生成した型定義
│       ├── types/
│       │   └── opencascade.d.ts    # opencascade.js の型宣言
│       └── pages/
│           ├── GalleryPage.tsx     # 一覧ページ（生成・選択・削除）
│           └── DetailPage.tsx      # 詳細ページ（3D・断面・STEP出力）
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_api.py                 # API エンドポイントの統合テスト
│   ├── test_compute_metrics.py     # メッシュ・プロファイル指標の算出テスト
│   ├── test_feasibility_metrics.py # カット後 feasibility 指標のテスト
│   ├── test_gene_generation.py     # 大量サンプル全件合格・seed 再現性テスト
│   ├── test_identify.py            # design_id の決定性・正規化テスト
│   ├── test_identify_extension.py  # 延長 gene の design_id テスト
│   ├── test_metrics.py             # metrics 算出のテスト
│   ├── test_physics.py             # 既知形状（球・円柱・円錐）の feasibility テスト
│   ├── test_profile_cut.py         # 傾斜カットのテスト
│   ├── test_profile_extension.py   # 上部延長のテスト
│   ├── test_storage.py             # SQLite CRUD のテスト
│   └── test_storage_patch.py       # PATCH 更新のテスト
├── scripts/
│   ├── dev.mjs                     # npm run dev のオーケストレータ
│   ├── stop.mjs                    # 孤児プロセス回収
│   ├── package-windows.ps1         # Windows zip 配布ビルド
│   └── debug_cut_zcog.py           # カットが z_cog_max に与える影響のデバッグ
├── data/
│   └── app.db                      # ローカル SQLite DB（git 管理外）
├── build/                          # PyInstaller 出力・配布 zip（git 管理外）
├── MATH_ROLY_POLY_TOY.md           # 起き上がりこぼしの数学的背景
├── oc-apis.txt                     # opencascade.js API リファレンス（ローカル用）
├── LICENSE
├── pyproject.toml                  # Python プロジェクト定義（uv 用）
├── package.json                    # ルートの npm scripts（dev / stop / package:windows）
├── package-lock.json
├── uv.lock
├── .python-version
└── roly-poly-toy-generator.spec    # PyInstaller 設定（git 管理外）
```
