import * as THREE from "three";
import { STLExporter } from "three/examples/jsm/exporters/STLExporter.js";

export function exportGeometryToStlBlob(
  geometry: THREE.BufferGeometry,
): Blob {
  const exporter = new STLExporter();
  const mesh = new THREE.Mesh(geometry);
  const stl = exporter.parse(mesh, { binary: true });
  // STLExporter は binary=true のとき DataView を返す
  if (stl instanceof DataView) {
    return new Blob([stl.buffer as ArrayBuffer], { type: "model/stl" });
  }
  // text fallback
  return new Blob([stl], { type: "model/stl" });
}

