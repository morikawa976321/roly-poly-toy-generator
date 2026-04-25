"""プロトタイプ全体で使う定数の定義。

v2 では gene のスキーマを「球キャップ底 + 5次多項式テーパ」のパラメトリック族
に置き換えた（底の平円盤は廃止、r(0)=0, r(height)=0 の両端0プロファイル）。
傾き θ_max=75° まで自己復元可能な形状のみを生成するための値域と安全余裕を、
ここに集約している。
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Final

# --- 形状の解像度 ------------------------------------------------------------

N_NODES: int = 64
"""r(z) プロファイル（折れ線）の制御点数。"""

REVOLVE_SEGMENTS: int = 128
"""プロファイルを z 軸回りに回転させて 3D メッシュ化するときの周方向セグメント数。"""

# --- 生成バッチ --------------------------------------------------------------

BATCH_SIZE: int = 12
"""1 回の generate リクエストで作成するデザイン数の既定値。"""

# --- 起き上がりこぼしの物理制約 ---------------------------------------------

TILT_MAX_DEG: float = 75.0
"""自己復元を保証する最大傾き角（deg）。接地点はこの角度までに対応する z* に移動する。"""

EPS_MM: float = 0.5
"""曲率半径に対する安全余裕（mm）。ρ_m - eps を実効曲率半径として評価する。"""

# --- パラメトリック形状族のパラメータ値域 ----------------------------------
#
# 形状: 底は半径 rb の球キャップ（cap_angle_deg まで）、中腹〜上部は
# 5 次多項式で C² に接続、上端半径は rt。全体高さは delta_target が
# 達成されるよう二分探索で調整する。

SPHERE_RB_MIN_MM: float = 20.0
SPHERE_RB_MAX_MM: float = 40.0
"""底側球面の半径（mm）。手のひらサイズに収める目安。"""

CAP_ANGLE_MIN_DEG: float = 78.0
CAP_ANGLE_MAX_DEG: float = 90.0
"""球キャップが底からどこまで続くか（極角, deg）。

接地点は傾き θ=TILT_MAX_DEG のときちょうど極角 θ の位置に来るので、
これが TILT_MAX_DEG より小さいと接地点がテーパ領域に入り feasibility が落ちる。
TILT_MAX_DEG+3° を下限とする。
"""

RT_RATIO_MIN: float = 0.0
RT_RATIO_MAX: float = 0.85
"""上端半径を、球キャップ終端半径 r_cap_end = rb·sin(cap_angle) に対する比で指定する。

上部の太さは揺れ周期や見た目の印象を大きく左右する重要な要素なので、固定
レンジ（[0, 4] mm 等）で縛らずに、球のサイズに対するスケール不変な比で
幅広く（ほぼ尖り〜ほぼずん胴）振る。上限を 1.0 未満にしておくのは、
``build_parametric_profile`` のテーパ区間で単峰性（r_cap_end 以降は非増加）
を保つため。

下限は 0.0（= 尖った先端）を許すが、これは上端接線角 ≈ 0°（水平着地）と
組み合わさった場合のみ：dr/dz=0 の 5 次多項式で r→0 に着地するので、3D では
「なだらかに先細る丸い指先」になる。上端接線角が非ゼロのときは、``sample_shape_params``
で rt_ratio 下限を自動で引き上げて尖りコーンを回避する（下の
``TOP_TANGENT_ANGLE_RT_FLOOR_SLOPE`` 参照）。
"""

TOP_TANGENT_ANGLE_MIN_DEG: float = 0.0
TOP_TANGENT_ANGLE_MAX_DEG: float = 65.0
TOP_TANGENT_ANGLE_ACTIVE_MIN_DEG: float = 10.0
TOP_TANGENT_ANGLE_FLAT_PROB: float = 0.15
"""上端における子午線の接線角（水平からの角度, deg）。

0° のとき上端は水平着地（= 底面が平らな円盤状の天面。従来の挙動）。
角度が大きいほど上端が外向きに落ち込み、肩が丸く下がった truncated dome 風になる。
上端を振ることは見た目のバリエーションだけでなく、慣性モーメント I を変えて
揺れ周期 T = 2π√((I+mR²)/(mg(R-h))) に直接効く。

``build_parametric_profile`` では dr/dz|_{z=height} = -tan(angle) としてこの角度を
5 次多項式の端点条件に注入する。角度は「ほぼフラット」と「しっかり肩が落ちる」
の二峰でサンプルし、一覧サムネでも差が見えるようにする。65° を上限にしているのは:

- それ以上急テーパにすると、5 次多項式が中腹で波打って二峰化する余地が増える
  （モノトニッククランプで救うが、見た目がぎこちなくなる）。
- 65° まで使うと、小さなカード表示でも「平たい天面」と「明確に絞れた上部」の
  差が視認しやすい。

なお feasibility（自己復元条件）は登り区間（r' ≥ cot(75°)）でのみ評価されるため、
上端の接線角は feasibility に影響しない。
"""

TOP_TANGENT_ANGLE_RT_FLOOR_SLOPE: float = 0.14
"""上端接線角 α と rt_ratio 下限のカップリング係数。

rt_ratio_min_eff = max(RT_RATIO_MIN, TOP_TANGENT_ANGLE_RT_FLOOR_SLOPE * tan(α))

と効かせて、α が大きいときは rt_ratio が 0 付近にならないようにする。α>0 かつ
rt=0 だと 3D 上で円錐の頂点（尖ったコーン）になるため。α=65° なら tan≈2.14 で
rt_ratio 下限は約 0.30 になる（= 球キャップ終端半径の 30% 以上を上端半径として残す）。
上端を細くできる余地を残しつつ、rt=0 での鋭いコーンだけを避ける“弱め”のガードにする。
"""

PEAK_Z_RATIO_MIN: float = 0.30
PEAK_Z_RATIO_MAX: float = 0.92
"""球キャップ終端 z_cap_end から上端 height までの区間で、最大半径（ピーク）が現れる
位置を割合で指定する。

z_peak = z_cap_end + PEAK_Z_RATIO * (height - z_cap_end)

従来は「球キャップ終端が最大半径」だったため半球っぽさが強かった。ピーク位置を
上に動かせるようにして、肩・くびれ・上膨れなどのバリエーションを作る。
"""

PEAK_R_RATIO_MIN: float = 1.06
PEAK_R_RATIO_MAX: float = 1.32
"""ピーク半径 r_peak を、球キャップ終端半径 r_cap_end に対する比で指定する。

r_peak = PEAK_R_RATIO * r_cap_end

1.0 を少し超えることで、球キャップの“続き”ではない上部の膨らみを作れる。
上限を抑えるのは、急激な張り出し（見た目の破綻・薄肉時の印刷性悪化）を避けるため。
"""

PEAK_CURVATURE_KAPPA_MIN: float = 0.35
PEAK_CURVATURE_KAPPA_MAX: float = 1.8
"""ピーク（最大半径）近傍の丸みを決める無次元係数 κ。

ピークで dr/dz=0 を強制しただけだと“平らな台地”になりやすいので、r''(z_peak) を負に
して、最大点としての丸みを与える。実装では

    r''(z_peak) = - κ * r_peak / L^2

とし、L は左右区間長の小さい方を使う（局所的に鋭くならない保守的スケール）。
κ が大きすぎると尖った肩になりやすいので上限を低めに抑える。
"""

PEAK_ACTIVE_PROB: float = 0.75
"""案A（ピークを球キャップ終端より上に置く形）を有効化する確率。

feasibility は主に登り区間の曲率・傾きに敏感で、ピーク形状を攻めすぎると
不合格率が上がる。まずは 35% 程度で混ぜ、残りは旧挙動（ピーク=球キャップ終端）
にして「一発 feasible」が十分高い状態を維持する。
"""

HEIGHT_HI_RB_FACTOR: float = 5.5
"""tune_height_for_delta の初期探索上限を rb に対する倍率で与える。

従来の 2.5 だと “背が高い・細長い” 個体が出にくいので、上限を広げて許容する。
二分探索は「高くするほど重心が上がる → delta が小さくなる」という単調性に依存するが、
この形状族では実用上十分に単調なので、探索レンジを広げても安定して動く。
"""

HEIGHT_OPT_GRID_POINTS: int = 40
"""高さ最適化（案C）で評価する候補点数（粗探索）。"""

HEIGHT_OPT_REFINE_POINTS: int = 18
"""高さ最適化（案C）の局所再探索で評価する候補点数。"""

HEIGHT_OPT_W_SLENDER: float = 1.0
HEIGHT_OPT_W_FEAS: float = 0.12
HEIGHT_OPT_W_DELTA: float = 0.08
HEIGHT_OPT_W_DELTA_UNDER: float = 0.25
"""高さ最適化（案C）のスコア重み。

- slender: height/(2*max_r)。細長さを直接押す
- feas: worst_margin（mm）を正規化して加点（形状単独で成立しやすいものを優先）
- delta: |delta-delta_target| を正規化して減点（目標から外れすぎないように）
- delta_under: delta < delta_target の不足分を強めに減点（復元余裕を残す）
"""

CAP_DOMINANCE_MAX_FRACTION: float = 0.62
"""「半球の下半分っぽい」形を弾くための球キャップ支配率の上限。

球キャップ部分の高さ z_cap_end が全高 height に占める割合

    cap_fraction = z_cap_end / height

が大きいほど、見た目が「下に凸の半球（もしくはそれの下半分）」に寄りやすい。
案Cでは height を探索して選べるので、cap_fraction が大きすぎる候補 height は
強制的に不採用にする。
"""

CAP_TOP_MIN_MM: float = 10.0
"""球キャップ終端から上端までに最低限必要な“上部の長さ”（mm）。

height - z_cap_end が短いと、上部の形状自由度（ピーク・肩・くびれ）が出せず、
半球っぽい塊に寄る。これも候補 height の強いフィルタとして使う。
"""

DELTA_TARGET_MIN_MM: float = 4.0
DELTA_TARGET_MAX_MM: float = 12.0
"""狙いの delta = rb - z_com（mm）。

θ_max=75° での安定余裕 eps_mm を確保するには
    delta > 2 * eps_mm / cos(TILT_MAX_DEG) ≈ 2 * 0.5 / 0.2588 ≈ 3.87 mm
が数学下限。余裕を見て 4.0 mm 以上を要求する。
"""

# --- gene 生成の細かい設定 ---------------------------------------------------

JITTER_AMP: float = 0.015
"""パラメトリック生成した radii に加える摂動の振幅（peak_radius 比）。

60° 版より小さく（0.02→0.015）：ギリギリ合格の個体が摂動で不合格化するのを防ぐ。
"""

FEASIBILITY_MAX_RETRY: int = 100
"""feasibility 不合格だったときの再サンプル上限。"""

# --- ID / gene の正規化設定 --------------------------------------------------

GENE_VERSION: int = 2
"""gene のスキーマバージョン。v1 は折れ線ランダム、v2 は球キャップ+テーパ。"""

GENE_FLOAT_DECIMALS: int = 4
DESIGN_ID_HEX_LENGTH: int = 16

# --- レガシー（v1 互換保持用）------------------------------------------------

BOTTOM_RADIUS_MM: float = 0.0
"""v2 では底面も r=0 に収束させる（球キャップ）。値は互換のため残し 0.0 固定。"""

# v1 で使っていた peak radius レンジは v2 では直接使わない（パラメトリック族が
# 代替）が、旧 gene の読み出しやテスト用途のため定数自体は残す。
PEAK_RADIUS_MIN_MM: float = 15.0
PEAK_RADIUS_MAX_MM: float = 40.0

HEIGHT_MIN_MM: float = 30.0
HEIGHT_MAX_MM: float = 80.0

# --- パス --------------------------------------------------------------------

REPO_ROOT: Path = Path(__file__).resolve().parents[2]

# --- ローカルアプリ設定 -------------------------------------------------------

APP_NAME: Final[str] = "roly-poly-toy-generator"
LOCAL_DATA_DIRNAME: Final[str] = "data"
LOCAL_CACHE_DIRNAME: Final[str] = "cache"
LOCAL_DB_FILENAME: Final[str] = "app.db"
IDLE_SHUTDOWN_SECONDS: Final[int] = 10 * 60


def load_environment() -> None:
    """互換用フック。

    ローカル配布版では外部サービス用の環境変数を使わない。既存の起動境界から
    呼ばれても副作用がないように、空実装として残す。
    """


def app_base_dir() -> Path:
    """書き込み可能なアプリ配置ディレクトリを返す。

    PyInstaller で exe 化された場合は exe の隣、開発時はリポジトリルートを使う。
    """

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return REPO_ROOT


def local_data_dir() -> Path:
    return app_base_dir() / LOCAL_DATA_DIRNAME


def local_cache_dir() -> Path:
    return local_data_dir() / LOCAL_CACHE_DIRNAME


def sqlite_db_path() -> Path:
    return local_data_dir() / LOCAL_DB_FILENAME


def frontend_dist_dir() -> Path:
    """配布zip同梱の `frontend/dist` を探す。

    zip配布では exe の隣に `frontend/dist` を置く。開発時は同じ関数で
    リポジトリ内の `frontend/dist` を参照する。
    """

    return app_base_dir() / "frontend" / "dist"
