import React from "react";
import { readableLink } from './links';

/**
 * Safe lightweight formatting for assistant/user text. Builds React nodes only
 * (never HTML strings): paragraphs, bullet/numbered lists, **bold**, `code`,
 * and http(s) links. Direction is resolved per block so mixed Persian/English
 * messages are not forced into one direction.
 */
const INLINE = /(\*\*[^*\n]+\*\*|`[^`\n]+`|https?:\/\/[^\s<>()]+[^\s<>().,;:!?،؛"'])/g;

function inline(text: string, keyBase: string, titles: Record<string, string>): React.ReactNode[] {
  return text.split(INLINE).filter(Boolean).map((part, index) => {
    const key = `${keyBase}-${index}`;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return <strong key={key}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) return <code key={key} className="ident">{part.slice(1, -1)}</code>;
    if (/^https?:\/\//i.test(part)) return <a key={key} href={part} title={part} target="_blank" rel="noopener noreferrer" className="rt-link" dir="auto">{readableLink(part, titles)}</a>;
    return <React.Fragment key={key}>{part}</React.Fragment>;
  });
}

export function RichText({ text, linkTitles = {} }: { text: string; linkTitles?: Record<string, string> }) {
  const blocks = text.replace(/\r\n/g, "\n").split(/\n{2,}/).map(block => block.trimEnd()).filter(block => block.trim());
  return <div className="rt">{blocks.map((block, index) => {
    const lines = block.split("\n");
    if (lines.every(line => /^\s*[-*•]\s+/.test(line))) return <ul key={index} dir="auto" className="bidi">{lines.map((line, i) => <li key={i}>{inline(line.replace(/^\s*[-*•]\s+/, ""), `${index}-${i}`, linkTitles)}</li>)}</ul>;
    if (lines.every(line => /^\s*\d+[.)]\s+/.test(line))) return <ol key={index} dir="auto" className="bidi">{lines.map((line, i) => <li key={i}>{inline(line.replace(/^\s*\d+[.)]\s+/, ""), `${index}-${i}`, linkTitles)}</li>)}</ol>;
    return <p key={index} dir="auto" className="bidi">{lines.map((line, i) => <React.Fragment key={i}>{i > 0 ? <br/> : null}{inline(line, `${index}-${i}`, linkTitles)}</React.Fragment>)}</p>;
  })}</div>;
}
