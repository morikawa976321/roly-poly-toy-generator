# roly-poly-toy-generator

A generator and curated gallery of physically stable, self-righting 3D models.

> 設計方針と決定事項は [`DESIGN_DECISIONS.md`](./DESIGN_DECISIONS.md) にまとまっている。

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
