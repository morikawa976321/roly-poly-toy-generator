-- Initial schema for roly-poly-toy-generator (Supabase Postgres)

create table if not exists public.designs (
  design_id               text primary key,
  gene                    jsonb not null,
  volume                  double precision not null,
  height                  double precision not null,
  max_width               double precision not null,
  centroid_z              double precision not null,
  z_cog_suggested         double precision,
  bottom_curvature_radius double precision,
  z_cog_max               double precision,
  created_at              timestamptz not null default now()
);

create index if not exists designs_created_at_idx
  on public.designs (created_at desc, design_id desc);

