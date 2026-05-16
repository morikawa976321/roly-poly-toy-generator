"""gene から decisive（決定的）に design_id を導出する。

ルール（README.md 参照）:
- gene を正規形の JSON 文字列にする（キーをソート、浮動小数は
  ``GENE_FLOAT_DECIMALS`` 桁で丸める）。
- SHA-256 でハッシュし、先頭 ``DESIGN_ID_HEX_LENGTH`` 桁の 16 進を取る。

これによって、プラットフォーム・Python のバージョン・dict への挿入順序に
依らず、同じ gene には同じ短い ID が付く。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

from .config import DESIGN_ID_HEX_LENGTH, GENE_FLOAT_DECIMALS
from .models import Gene


def _round_floats(obj: Any, decimals: int) -> Any:
    if isinstance(obj, float):
        return round(obj, decimals)
    if isinstance(obj, list):
        return [_round_floats(v, decimals) for v in obj]
    if isinstance(obj, dict):
        return {k: _round_floats(v, decimals) for k, v in obj.items()}
    return obj


def canonical_gene_dict(gene: Gene) -> Dict[str, Any]:
    raw = gene.model_dump()
    # 延長量は保存用パラメータであり、形状本体の ID には含めない。
    raw.pop("top_extension_mm", None)
    raw.pop("top_cut_height_mm", None)
    raw.pop("top_cut_angle_deg", None)
    return _round_floats(raw, GENE_FLOAT_DECIMALS)


def canonical_gene_json(gene: Gene) -> str:
    return json.dumps(
        canonical_gene_dict(gene),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def design_id_for(gene: Gene) -> str:
    payload = canonical_gene_json(gene).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return digest[:DESIGN_ID_HEX_LENGTH]
