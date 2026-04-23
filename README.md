# roly-poly-toy-generator

A generator and curated gallery of physically stable, self-righting 3D models.

> 設計方針と決定事項は [`DESIGN_DECISIONS.md`](./DESIGN_DECISIONS.md) にまとまっている。

## 構成

- `backend/` — Python + FastAPI。gene の生成、断面 SVG / GLB の生成、SQLite への保存を担当。
- `frontend/` — Vite + React + TypeScript + Tailwind v4 + react-three-fiber。一覧 (SVG サムネ) と 詳細 (3D ビュー) を提供。
- `data/` — ランタイム状態（`app.db` と `assets/{design_id}/{thumb.svg,model.glb}`）。gitignored。

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

終了はターミナルで `Ctrl+C`。`npm run dev` はオーケストレータが `SIGINT` を拾って backend / frontend のプロセスツリーを `taskkill /T /F` で落とすので、`uvicorn --reload` の子プロセスまでまとめて終了する。

ターミナルを強制終了して `:8000` や `:5173` を握ったままの孤児が残った場合は、次で回収できる。

```powershell
npm run stop
```

## API

| Method | Path                                    | 用途                          |
| ------ | --------------------------------------- | ----------------------------- |
| POST   | `/api/designs/generate`                 | N 個のデザインを生成          |
| GET    | `/api/designs?limit=..&offset=..`       | 一覧（新しい順）              |
| GET    | `/api/designs/{id}`                     | 詳細（gene + metrics + URL） |
| GET    | `/api/designs/{id}/thumb.svg`           | 断面サムネ                    |
| GET    | `/api/designs/{id}/model.glb`           | 3D モデル                     |

OpenAPI は `http://localhost:8000/docs` で参照可能。
