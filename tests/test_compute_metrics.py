"""compute_metrics が延長・カットを固体メトリクスに反映すること。"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.metrics import compute_metrics
from backend.app.models import Gene
from backend.app.profile_extension import max_top_extension_mm


@pytest.fixture
def docs_gene() -> Gene:
    path = Path("docs/designs/6d7afe17fed27c7c/gene.json")
    if not path.is_file():
        pytest.skip("docs design gene missing")
    return Gene.model_validate_json(path.read_text())


def test_extension_and_cut_affect_volume_and_centroid(docs_gene: Gene) -> None:
    dmax = max_top_extension_mm(docs_gene)
    base = compute_metrics(docs_gene)
    extended = compute_metrics(
        docs_gene.model_copy(update={"top_extension_mm": dmax})
    )
    cut = compute_metrics(
        docs_gene.model_copy(
            update={
                "top_extension_mm": dmax,
                "top_cut_height_mm": 50.0,
                "top_cut_angle_deg": 35.0,
            }
        )
    )

    assert extended.volume != pytest.approx(base.volume, rel=0.01)
    assert extended.centroid_z != pytest.approx(base.centroid_z, abs=0.5)
    assert cut.volume < extended.volume
    assert cut.centroid_z != pytest.approx(extended.centroid_z, abs=0.5)
    assert cut.z_cog_max is not None
    assert base.z_cog_max is not None
