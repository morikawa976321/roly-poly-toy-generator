"""
gene から決定的 design_id を導出。

役割: 形状本体（延長・カット除く）の正規化ハッシュ ID。
働き: gene をキーソート・浮動小数丸めの JSON にし SHA-256 先頭 hex を返す。``api`` / ``storage`` の主キーに使う。
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
