"""API 層で使う Pydantic モデル群。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class Gene(BaseModel):
    """デザインの形状を正規化した表現。

    形状は、[0, height] 上の ``N`` 個の制御点 (z_i, radii[i]) による
    折れ線/スプライン r(z) プロファイルを z 軸回りに回転させた回転体として定義する。
    z_i の配置は ``z_warp`` で決まる:

        z_i = height · (i / (N-1)) ** z_warp

    - ``z_warp=1.0`` ないし ``None``: 等間隔（v1 および旧 v2）
    - ``z_warp=2.0``: 二乗ワープ。z=0 付近にノードが密に集まり、球キャップの
       √z 型特異点（極で傾き無限大）を忠実に再現できる。v2 では既定値。

    バージョン:
    - v1（旧）: radii[0] == bottom_radius（> 0、底は平円盤）、radii[-1] == 0、
      z_warp は未設定（None → 等間隔扱い）。
    - v2（現行、GENE_VERSION=2）: radii[0] == 0（底は球キャップの極点）、
      radii[-1] == rt（上端の丸め半径）、球キャップ+5次テーパのパラメトリック族
      から生成され、θ_max=75° まで自己復元可能な形状のみ。z_warp=2.0。

    両バージョンとも radii は単峰（ある peak index までは単調増加、以降は単調減少）。

    ``top_extension_mm`` はベース形状（radii / height）を変えずに上方向へ
    付与する延長量（mm）。0 でベース形状のみ。
    """

    version: int
    N: int
    height: float
    bottom_radius: float
    """v1: 底面半径（> 0）。v2: 常に 0（球キャップ極点）。互換のため残す。"""

    radii: List[float]

    z_warp: Optional[float] = None
    """z_nodes の配置指数。``z_i = height · (i/(N-1))**z_warp``。

    None / 1.0 で等間隔（v1 互換）。2.0 で z=0 付近を密にサンプルし、
    球キャップの極での √z 型特異点を忠実に表現する（v2 既定）。
    """

    top_extension_mm: float = 0.0
    """ベース形状の上端からの延長量（mm）。design_id ハッシュには含めない。"""

    top_cut_height_mm: float = 0.0
    """斜めカット平面が z 軸と交わる高さ（mm）。design_id ハッシュには含めない。"""

    top_cut_angle_deg: float = 0.0
    """カット平面の傾き（度, 水平=0）。正で外側ほど z 上限が高い。design_id には含めない。"""


class Metrics(BaseModel):
    volume: float
    height: float
    max_width: float
    centroid_z: float

    bottom_curvature_radius: Optional[float] = None
    """南極近傍の有効曲率半径（mm）。v2 gene では rb にほぼ等しい。"""

    z_cog_max: Optional[float] = None
    """θ_max（既定 75°）まで自己復元できる z_CoG の上限（mm）。

    実際の設計では z_CoG < z_cog_max を満たす必要がある。None は未計算 or v1 gene。
    """


class DesignSummary(BaseModel):
    """一覧ビュー向けの最小情報。"""

    design_id: str
    gene: Gene
    metrics: Metrics
    created_at: str


class DesignDetail(BaseModel):
    """詳細ビュー向けのフル情報。"""

    design_id: str
    gene: Gene
    metrics: Metrics
    created_at: str


class GenerateRequest(BaseModel):
    n: Optional[int] = Field(default=None, ge=1, le=200)
    parent_ids: Optional[List[str]] = Field(default=None, max_length=4)


class GenerateResponse(BaseModel):
    designs: List[DesignSummary]


class ListResponse(BaseModel):
    designs: List[DesignSummary]
    total: int


class DeleteAllResponse(BaseModel):
    deleted: int


class PatchDesignRequest(BaseModel):
    top_extension_mm: float = Field(ge=0.0)
    top_cut_height_mm: float = Field(ge=0.0)
    top_cut_angle_deg: float = Field(ge=-89.0, le=89.0)
