import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'FigPrism · 科研图表灵感库', description: '从优秀论文图表中发现构图、配色与研究灵感。' };
export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) { return <html lang="zh-CN"><body>{children}</body></html>; }
