export type User = { id: number; username: string; role: "admin" | "user" };
export type Color = {
  hex: string;
  rgb: number[];
  weight: number;
  l: number;
  c: number;
  h: number;
};
export type Palette = {
  colors: Color[];
  pairs: { fill: string; stroke: string }[];
  neutrals: string[];
  buckets: string[];
};
export type Subitem = {
  id: string;
  label: string;
  caption: string;
  norm_bbox: number[];
  palette: Palette;
  has_raw: boolean;
};
export type Figure = {
  id: string;
  paper_id: string;
  title: string;
  authors: string[];
  abstract: string;
  caption: string;
  fig_label: string;
  page_number: number;
  bbox: number[];
  archetype: string;
  span_type: string;
  layout_type: string;
  venue: string;
  venue_year: number | null;
  venue_tier: string | null;
  hf_upvotes: number;
  arxiv_id: string | null;
  domains: string[];
  source_urls: Record<string, string>;
  width: number;
  height: number;
  aspect_ratio: number;
  blurhash: string;
  fonts: string[];
  palette: Palette;
  subitems: Subitem[];
  sub_tags: string[];
  tikz_code: string | null;
  extract_method: string;
  confidence: number;
  review_status: string;
  version_hash: string;
  thumb_url: string;
  hd_url: string;
  raw_url: string;
  viewed_at?: string;
  collection_item?: { user_note: string; focused_subitem_id: string | null };
};
export type Domain = {
  slug: string;
  name: string;
  color_dot: string;
  sub_tags: string[];
  phrases: string[];
  acronyms: string[];
  exclude_terms: string[];
  arxiv_cats: string[];
  vlm_criteria: string;
  is_active: boolean;
};
export type Board = {
  id: string;
  name: string;
  description: string;
  count: number;
  items?: Figure[];
};
export type Job = {
  id: string;
  kind: string;
  status: string;
  progress: number;
  message: string;
  created_at: string;
};
export type FigurePage = {
  items: Figure[];
  total: number;
  next_offset: number | null;
};
export const archetypes = [
  "Teaser",
  "Pipeline",
  "Micro-Mechanism",
  "Curve",
  "Bar",
  "Scatter/Radar",
  "Heatmap",
  "Case Study",
];
export const archetypeNames: Record<string, string> = {
  Teaser: "概念总览",
  Pipeline: "方法框架",
  "Micro-Mechanism": "局部机制",
  Curve: "折线 / Scaling",
  Bar: "柱状 / 消融",
  "Scatter/Radar": "散点 / 雷达",
  Heatmap: "热力分布",
  "Case Study": "定性案例",
};

export type PaperGroup = {
  paper: Pick<
    Figure,
    | "title"
    | "authors"
    | "abstract"
    | "venue"
    | "venue_year"
    | "venue_tier"
    | "hf_upvotes"
    | "layout_type"
    | "source_urls"
    | "domains"
    | "arxiv_id"
  > & { id: string };
  hero_figure_id: string;
  matched_figures: Figure[];
};
export type FeedPage = {
  group_by: "paper" | "none";
  items: PaperGroup[] | Figure[];
  total: number;
  total_papers: number;
  total_figures: number;
  next_offset: number | null;
};
