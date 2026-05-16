from backend.app.identify import design_id_for
from backend.app.models import Gene


def test_top_extension_mm_excluded_from_design_id():
    base = Gene(
        version=2,
        N=5,
        height=30.0,
        bottom_radius=0.0,
        radii=[0.0, 5.0, 10.0, 5.0, 0.0],
        z_warp=2.0,
        top_extension_mm=0.0,
    )
    extended = base.model_copy(update={"top_extension_mm": 10.0})
    assert design_id_for(base) == design_id_for(extended)
