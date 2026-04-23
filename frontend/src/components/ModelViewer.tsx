import { useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { Bounds, OrbitControls } from "@react-three/drei";
import type { Gene } from "../types";
import { latheGeometryFromGene } from "../derive/mesh";

type Props = {
  gene: Gene;
  centroidZ: number;
  height: number;
};

function ToyMesh({ gene }: { gene: Gene }) {
  const geom = useMemo(() => latheGeometryFromGene(gene, 128), [gene]);
  return (
    <mesh geometry={geom} castShadow receiveShadow>
      <meshStandardMaterial color="#94a3b8" metalness={0.05} roughness={0.9} />
    </mesh>
  );
}

function CentroidMarker({
  centroidZ,
  height,
}: {
  centroidZ: number;
  height: number;
}) {
  const radius = useMemo(() => Math.max(0.5, height * 0.02), [height]);
  return (
    <mesh position={[0, 0, centroidZ]}>
      <sphereGeometry args={[radius, 24, 24]} />
      <meshStandardMaterial color="#ef4444" emissive="#7f1d1d" />
    </mesh>
  );
}

export default function ModelViewer({ gene, centroidZ, height }: Props) {
  return (
    <div className="w-full h-[480px] rounded-lg border border-slate-200 bg-white overflow-hidden">
      <Canvas
        camera={{ position: [120, 120, 120], fov: 40, up: [0, 0, 1] }}
        dpr={[1, 2]}
      >
        <ambientLight intensity={0.6} />
        <directionalLight position={[100, 100, 200]} intensity={0.8} />
        <directionalLight position={[-100, -100, 50]} intensity={0.3} />
        <Bounds fit clip observe margin={1.2}>
          <group>
            <ToyMesh gene={gene} />
            <CentroidMarker centroidZ={centroidZ} height={height} />
          </group>
        </Bounds>
        <OrbitControls makeDefault target={[0, 0, height / 2]} />
        <axesHelper args={[Math.max(20, height * 0.5)]} />
      </Canvas>
    </div>
  );
}
