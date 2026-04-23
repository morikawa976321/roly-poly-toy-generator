import { createContext, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

// 曲線生成ロジックの比較用（一時的）。バックエンドの SmoothingMethod と値が一致している必要がある。
export type SmoothingMethod = "bspline" | "gaussian";

export const SMOOTHING_OPTIONS: {
  value: SmoothingMethod;
  label: string;
  description: string;
}[] = [
  {
    value: "bspline",
    label: "Cubic B-spline",
    description: "radii を制御多角形とする 3 次 B-スプライン（C² 滑らか）",
  },
  {
    value: "gaussian",
    label: "Gaussian smoothing",
    description: "折れ線を密サンプル後に 1D ガウシアンで平滑化",
  },
];

type Ctx = {
  smoothing: SmoothingMethod;
  setSmoothing: (m: SmoothingMethod) => void;
};

const SmoothingContext = createContext<Ctx | null>(null);

export function SmoothingProvider({ children }: { children: ReactNode }) {
  const [smoothing, setSmoothing] = useState<SmoothingMethod>("gaussian");
  const value = useMemo(() => ({ smoothing, setSmoothing }), [smoothing]);
  return (
    <SmoothingContext.Provider value={value}>
      {children}
    </SmoothingContext.Provider>
  );
}

export function useSmoothing(): Ctx {
  const ctx = useContext(SmoothingContext);
  if (!ctx) {
    throw new Error("useSmoothing must be used within SmoothingProvider");
  }
  return ctx;
}

export function withSmoothingQuery(url: string, method: SmoothingMethod): string {
  if (method === "bspline") return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}smoothing=${method}`;
}
