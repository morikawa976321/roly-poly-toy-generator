"""カット・延長が z_cog_max に与える影響の ad-hoc デバッグ脚本。

役割: feasibility_metrics 不具合調査用の一時スクリプト。
働き: 直接実行で seed 固定 gene に対しカット高さスイープを標準出力する。pytest には含めない。
"""
import numpy as np
from backend.app.gene import sample_gene_with_feasibility
from backend.app.profile_extension import feasibility_profile, max_top_extension_mm
from backend.app.feasibility_metrics import feasibility_extras_for_gene
from backend.app.profile_cut import cut_profile_silhouette
from backend.app.physics import feasibility_from_profile
from backend.app.mesh_revolve import revolve_mesh
from backend.app.mesh_plane_cut import clip_mesh_below_plane, cut_would_change

gene, _ = sample_gene_with_feasibility(seed=7)
z, r = feasibility_profile(gene)
peak = int(np.argmax(r))
print("peak z", z[peak], "r", r[peak])

for cut_h in [5, 15, 25, 35, 45]:
    g = gene.model_copy(update={"top_cut_height_mm": cut_h, "top_cut_angle_deg": 35.0})
    e = feasibility_extras_for_gene(g)
    z2, r2 = feasibility_profile(g)
    sil = cut_profile_silhouette(z2, r2, cut_h, 35.0)
    for label, zm, rm in [("R", sil.z_right, sil.r_right), ("L", sil.z_left, sil.r_left)]:
        pk = int(np.argmax(rm))
        f = feasibility_from_profile(zm, rm, smooth_derivatives=True)
        z0, r0 = z2[: peak + 1], r2[: peak + 1]
        zm_asc = zm[: pk + 1]
        changed = len(zm_asc) != len(z0) or not np.allclose(zm_asc, z0[: len(zm_asc)], atol=0.05)
        print(f"  cut_h={cut_h} {label} z_cog={f.z_cog_max:.2f} asc_changed={changed} pk_z={zm[pk]:.1f}")

dmax = max_top_extension_mm(gene)
gext = gene.model_copy(update={"top_extension_mm": dmax})
z3, r3 = feasibility_profile(gext)
pk3 = int(np.argmax(r3))
print("extended peak z", z3[pk3], "top", z3[-1])
for cut_h in [10, 30, 50, 70, 90]:
    g = gext.model_copy(update={"top_cut_height_mm": cut_h, "top_cut_angle_deg": 35.0})
    e = feasibility_extras_for_gene(g)
    print(f"  ext cut_h={cut_h} z_cog_max={e['z_cog_max']}")

# mesh silhouette approach
z, r = feasibility_profile(gene)
verts, tris = revolve_mesh(z, r, 96)
if cut_would_change(verts, 25.0, np.tan(np.radians(35))):
    cut_v, cut_t = clip_mesh_below_plane(verts, tris, 25.0, 35.0)
    print("cut mesh verts", len(cut_v))
