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
  macro_category?: "method" | "data_chart" | "case_study";
  sub_type?: string;
  primary_style?: string | null;
  secondary_style?: string | null;
  layout_topology?: string | null;
  craft_badges?: string[];
  chart_layout?: string | null;
  style_confidence?: number | null;
  style_reason?: string | null;
  taxonomy_locked?: number;
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

export type TabBucketCount = { papers: number; figures: number };
export type TabCounts = {
  all: TabBucketCount;
  method: TabBucketCount;
  data_chart: TabBucketCount;
};

export const methodSubTypes: { key: string; label: string; short: string }[] = [
  { key: "concept_teaser", label: "💡 概念总览", short: "概念总览" },
  { key: "system_pipeline", label: "🏗️ 方法主框架", short: "方法主框架" },
  { key: "micro_mechanism", label: "🔬 局部算子机制", short: "局部机制" },
];

export const methodStyles: { key: string; label: string; short: string }[] = [
  { key: "plain_wireframe", label: "📐 朴素框图", short: "朴素框图" },
  { key: "clean_iconic", label: "🌿 清新图标", short: "清新图标" },
  { key: "refined_gradient", label: "✨ 高级渐变", short: "高级渐变" },
  { key: "dense_panoramic", label: "🍱 稠密全景", short: "稠密全景" },
  { key: "bold_contrast", label: "⚡ 大开大合", short: "大开大合" },
  { key: "tensor_schematic", label: "🧮 张量数理", short: "张量数理" },
  { key: "isometric_3d", label: "🧊 立体轴测", short: "立体轴测" },
  { key: "editorial_minimal", label: "📰 刊物极简", short: "刊物极简" },
];

export const methodTopologies: { key: string; label: string; short: string }[] = [
  { key: "linear_pipeline", label: "➡️ 串联流水线", short: "串联流水线" },
  { key: "macro_zoom_in", label: "🔍 局部放大展开", short: "局部放大" },
  { key: "ab_comparison", label: "⚖️ 正反双轨对比", short: "正反对比" },
  { key: "modular_swimlane", label: "🪟 多阶段分栏", short: "多阶段分栏" },
  { key: "cyclic_loop", label: "🔄 循环博弈闭环", short: "循环闭环" },
  { key: "branching_tree", label: "🌿 分支/采样树", short: "分支采样树" },
];

export const methodCrafts: { key: string; label: string; short: string }[] = [
  { key: "frozen_trainable_marks", label: "❄️🔥 冻结/可训标识", short: "冻结/可训" },
  { key: "hybrid_mini_chart", label: "📊 图+实验混排", short: "图+实验混排" },
  { key: "embedded_prompt_card", label: "💬 Prompt 卡片", short: "Prompt 卡片" },
  { key: "dedicated_legend_box", label: "🗂️ 独立图例框", short: "独立图例框" },
];

export const dataChartTypes: { key: string; label: string; short: string }[] = [
  { key: "line_scaling", label: "📈 折线 / Scaling", short: "折线 / Scaling" },
  { key: "bar_ablation", label: "📊 柱状 / 消融与胜率", short: "柱状 / 消融" },
  { key: "scatter_pareto", label: "🎯 帕累托 / 散点气泡", short: "帕累托 / 散点" },
  { key: "radar_polar", label: "🕸️ 多维雷达图", short: "多维雷达图" },
  { key: "distribution_density", label: "🎻 分布 / 箱线 / 密度", short: "分布 / 箱线" },
  { key: "heatmap_matrix", label: "🟧 热力 / 矩阵图", short: "热力 / 矩阵图" },
];

export const dataChartLayouts: { key: string; label: string; short: string }[] = [
  { key: "single_plot", label: "🖼️ 单图特写", short: "单图特写" },
  { key: "multi_panel_grid", label: "田 多子图网格 (1×N / 2×2)", short: "多子图网格" },
  { key: "inset_zoom", label: "🔎 带局部放大窗 (Inset)", short: "局部放大窗" },
  { key: "combo_dual_axis", label: "🔀 双轴 / 柱线组合", short: "双轴组合" },
];

export const subTypeShortNames: Record<string, string> = Object.fromEntries([
  ...methodSubTypes.map((x) => [x.key, x.short]),
  ...dataChartTypes.map((x) => [x.key, x.short]),
  ["qualitative_case", "定性案例"],
]);

export const styleShortNames: Record<string, string> = Object.fromEntries(
  methodStyles.map((x) => [x.key, x.short]),
);
export const topologyShortNames: Record<string, string> = Object.fromEntries(
  methodTopologies.map((x) => [x.key, x.short]),
);
export const craftShortNames: Record<string, string> = Object.fromEntries(
  methodCrafts.map((x) => [x.key, x.short]),
);
export const chartLayoutShortNames: Record<string, string> = Object.fromEntries(
  dataChartLayouts.map((x) => [x.key, x.short]),
);

export function figureTypeLabel(f: Pick<Figure, "sub_type" | "archetype">): string {
  if (f.sub_type && subTypeShortNames[f.sub_type]) {
    return subTypeShortNames[f.sub_type];
  }
  return archetypeNames[f.archetype] || f.archetype;
}

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
  tab_counts?: TabCounts;
  next_offset: number | null;
};
