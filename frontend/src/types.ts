export type Metrics = {
  volume: number;
  height: number;
  max_width: number;
  centroid_z: number;
  z_cog_suggested?: number | null;
  bottom_curvature_radius?: number | null;
  z_cog_max?: number | null;
};

export type DesignSummary = {
  design_id: string;
  metrics: Metrics;
  created_at: string;
};

export type Gene = {
  version: number;
  N: number;
  height: number;
  bottom_radius: number;
  radii: number[];
  z_warp?: number | null;
};

export type DesignDetail = {
  design_id: string;
  gene: Gene;
  metrics: Metrics;
  created_at: string;
  thumbnail_url: string;
  model_url: string;
};

export type ListResponse = {
  designs: DesignSummary[];
  total: number;
};

export type GenerateResponse = {
  designs: DesignSummary[];
};
