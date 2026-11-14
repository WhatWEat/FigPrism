"use client";
import { memo, useEffect, useState } from "react";
import "katex/dist/katex.min.css";

function Formula({ source }: { source: string }) {
  const [rendered, setRendered] = useState<{
    source: string;
    html: string;
  } | null>(null);
  const simple = /^([A-Za-z])_([A-Za-z]{2,})$/.exec(source);
  useEffect(() => {
    let active = true;
    const normalized = source.replace(
      /^([A-Za-z])_([A-Za-z]{2,})$/,
      "$1_{\\mathrm{$2}}",
    );
    import("katex")
      .then(({ default: katex }) => {
        const html = katex.renderToString(normalized, {
          trust: false,
          throwOnError: false,
          maxExpand: 200,
          maxSize: 8,
          strict: "ignore",
        });
        if (active) setRendered({ source, html });
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [source]);
  if (rendered?.source === source)
    return (
      <span
        className="caption-math"
        dangerouslySetInnerHTML={{ __html: rendered.html }}
      />
    );
  return (
    <span className="caption-math">
      {simple ? (
        <>
          {simple[1]}
          <sub>{simple[2]}</sub>
        </>
      ) : (
        source
      )}
    </span>
  );
}

export const RichCaption = memo(function RichCaption({
  text,
  onFocus,
}: {
  text: string;
  onFocus: (id: string) => void;
}) {
  // Only explicit math delimiters are interpreted; ordinary caption text remains React text.
  return (
    <>
      {text
        .split(/(\$[^$\n]+\$|\\\([\s\S]*?\\\)|\([a-i]\))/g)
        .map((part, index) => {
          if (part.startsWith("$") && part.endsWith("$"))
            return <Formula key={index} source={part.slice(1, -1)} />;
          if (part.startsWith("\\(") && part.endsWith("\\)"))
            return <Formula key={index} source={part.slice(2, -2)} />;
          if (/^\([a-i]\)$/.test(part))
            return (
              <button
                key={index}
                className="caption-anchor"
                onClick={() => onFocus(part[1])}
              >
                {part}
              </button>
            );
          return part;
        })}
    </>
  );
});
