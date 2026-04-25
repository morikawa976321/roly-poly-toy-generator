"""`backend/app/identify.py` の `design_id_for` の安定性テスト。

永続化キー（design_id）は入力 gene から決定的に導出されるため、
- 同一 gene → 常に同一 ID
- dict 挿入順やバージョン差に依存しない
- `GENE_FLOAT_DECIMALS` 桁より細かい差は吸収される
- `GENE_FLOAT_DECIMALS` 桁で区別される差は ID を変える
を保証する必要がある（これが崩れると同じ形が重複保存され、ID 衝突 or 無限ループに繋がる）。
"""

from __future__ import annotations

from typing import Any, Dict

from backend.app.config import DESIGN_ID_HEX_LENGTH, GENE_FLOAT_DECIMALS
from backend.app.identify import canonical_gene_json, design_id_for
from backend.app.models import Gene


def _gene(**overrides) -> Gene:
    data: Dict[str, Any] = dict(
        version=2,
        N=5,
        height=30.0,
        bottom_radius=0.0,
        radii=[0.0, 5.0, 10.0, 5.0, 0.0],
        z_warp=2.0,
    )
    data.update(overrides)
    return Gene(**data)


def test_design_id_has_expected_length_and_charset() -> None:
    did = design_id_for(_gene())
    assert isinstance(did, str)
    assert len(did) == DESIGN_ID_HEX_LENGTH
    assert all(c in "0123456789abcdef" for c in did)


def test_design_id_is_deterministic_for_same_gene() -> None:
    a = design_id_for(_gene())
    b = design_id_for(_gene())
    assert a == b


def test_design_id_is_insensitive_to_dict_insertion_order() -> None:
    data1 = {
        "version": 2,
        "N": 5,
        "height": 30.0,
        "bottom_radius": 0.0,
        "radii": [0.0, 5.0, 10.0, 5.0, 0.0],
        "z_warp": 2.0,
    }
    data2 = {
        "z_warp": 2.0,
        "radii": [0.0, 5.0, 10.0, 5.0, 0.0],
        "N": 5,
        "bottom_radius": 0.0,
        "height": 30.0,
        "version": 2,
    }
    g1 = Gene.model_validate(data1)
    g2 = Gene.model_validate(data2)
    assert design_id_for(g1) == design_id_for(g2)


def test_canonical_gene_json_sorts_keys() -> None:
    s = canonical_gene_json(_gene())
    # JSON object 開始直後は ASCII ソート順で一番小さいキー "N" が来る
    assert s.startswith('{"N":')


def test_design_id_unchanged_below_float_decimals_threshold() -> None:
    """GENE_FLOAT_DECIMALS 桁より細かい差は丸めで吸収され、ID は同じになる。"""
    eps = 10.0 ** (-(GENE_FLOAT_DECIMALS + 2))  # 桁下限より 2 桁下
    g1 = _gene(height=30.0)
    g2 = _gene(height=30.0 + eps)
    assert design_id_for(g1) == design_id_for(g2)


def test_design_id_changes_above_float_decimals_threshold() -> None:
    """GENE_FLOAT_DECIMALS 桁で区別できる差なら ID は必ず変わる。"""
    # 最下位桁の 2 ステップぶん（銀行丸めに引っかからない安全マージン）
    step = 2.0 * (10.0 ** -GENE_FLOAT_DECIMALS)
    g1 = _gene(height=30.0)
    g2 = _gene(height=30.0 + step)
    assert design_id_for(g1) != design_id_for(g2)


def test_design_id_changes_when_radii_change_above_threshold() -> None:
    step = 2.0 * (10.0 ** -GENE_FLOAT_DECIMALS)
    g1 = _gene()
    radii_mut = list(g1.radii)
    radii_mut[2] = radii_mut[2] + step
    g2 = _gene(radii=radii_mut)
    assert design_id_for(g1) != design_id_for(g2)
