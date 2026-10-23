import React from "react";
import { api, StudioConversation, StudioProject } from "../api";
import { useAuthenticatedMediaUrl } from "../AuthenticatedMedia";
import { Icon } from "../components/Icon";
import { ActivityBlock, ThinkingRow } from "./Activity";
import { RenderCard } from "./RenderCard";
import { RichText } from "./RichText";
import { TimelineItem } from "./model";

export interface LocalFileInfo { name: string; type: string; url: string }

/** Lazy preview for an attachment we only know by id: nothing downloads until asked. */
function RemoteAttachment({ conversationId, id, index, autoOpen }: { conversationId: string; id: string; index: number; autoOpen?: boolean }) {
  const [open, setOpen] = React.useState(Boolean(autoOpen));
  const url = useAuthenticatedMediaUrl(open ? api.studioAttachmentUrl(conversationId, id) : undefined);
  const [kind, setKind] = React.useState<"image" | "video" | "audio" | "">("");
  React.useEffect(() => {
    if (!url) return;
    let active = true;
    void fetch(url).then(r => r.blob()).then(blob => { if (active) setKind(blob.type.startsWith("image/") ? "image" : blob.type.startsWith("audio/") ? "audio" : "video"); }).catch(() => active && setKind("video"));
    return () => { active = false; };
  }, [url]);
  if (!open) return <button className="attach-chip attach-button" onClick={() => setOpen(true)}><span className="attach-icon"><Icon name="paperclip" size={16}/></span><span className="attach-meta"><b>Attachment {index + 1}</b><small>Tap to preview</small></span></button>;
  if (!url || !kind) return <div className="attach-chip"><span className="spinner"/><span className="attach-meta"><small>Loading preview…</small></span></div>;
  return <div className="attach-preview">{kind === "image" ? <img src={url} alt={`Attachment ${index + 1}`}/> : kind === "audio" ? <audio src={url} controls/> : <video src={url} controls playsInline preload="metadata"/>}</div>;
}

function Attachments({ conversationId, ids, local, autoOpen }: { conversationId?: string; ids: string[]; local?: LocalFileInfo[]; autoOpen?: boolean }) {
  if (local?.length) return <div className="msg-files">{local.map((file, index) => file.type.startsWith("image/")
    ? <div className="attach-preview" key={index}><img src={file.url} alt={file.name}/></div>
    : <div className="attach-chip" key={index}><span className="attach-icon"><Icon name={file.type.startsWith("video/") ? "video" : "music"} size={16}/></span><span className="attach-meta"><b className="wrap-safe">{file.name}</b></span></div>)}</div>;
  if (!ids.length || !conversationId) return null;
  return <div className="msg-files">{ids.map((id, index) => <RemoteAttachment key={id} conversationId={conversationId} id={id} index={index} autoOpen={autoOpen}/>)}</div>;
}

export function Thread({ items, conversation, projects, localFiles, thinking, compactRender, retryHref, onOpenPreview, onEditAgain, onChoice, onRetryMessage, sourceUrl, linkTitles = {} }: {
  items: TimelineItem[]; conversation: StudioConversation | null; projects: StudioProject[]; localFiles?: LocalFileInfo[];
  thinking?: string; compactRender?: boolean; retryHref?: string; onOpenPreview: (projectId: string) => void; onEditAgain: (projectId: string) => void;
  onChoice: (choice: string) => void; onRetryMessage: () => void; sourceUrl?: string; linkTitles?: Record<string, string>;
}) {
  return <ol className="thread" aria-label="Conversation">
    {items.map(item => {
      if (item.kind === "message") return <li key={item.id} className={`msg msg-${item.role}`} data-pending={item.pending || undefined}>
        {item.role === "user"
          ? <div className="bubble">
              <Attachments conversationId={conversation?.id} ids={item.attachments} local={item.pending || item.failed ? localFiles : undefined}/>
              {item.content ? <RichText text={item.content} linkTitles={linkTitles}/> : null}
              {item.failed ? <div className="msg-failed"><Icon name="alert" size={14}/>Not sent <button className="link-btn" onClick={onRetryMessage}>Retry</button></div> : null}
            </div>
          : <div className="assistant"><span className="assistant-mark" aria-hidden="true"><Icon name="spark" size={13}/></span><div className="assistant-body"><RichText text={item.content} linkTitles={linkTitles}/><Attachments conversationId={conversation?.id} ids={item.attachments} autoOpen/></div></div>}
      </li>;
      if (item.kind === "activity") return <li key={item.id} className="thread-aux"><ActivityBlock steps={item.steps} live={item.live} retryHref={retryHref}/></li>;
      if (item.kind === "render") {
        const project = projects.find(p => p.id === item.projectId);
        return project ? <li key={item.id} className="thread-aux"><RenderCard project={project} sourceUrl={sourceUrl} startedAt={item.startedAt} compact={compactRender} onOpenPreview={() => onOpenPreview(project.id)} onEditAgain={() => onEditAgain(project.id)} retryHref={retryHref}/></li> : null;
      }
      if (item.kind === "question") return item.choices.length && !item.style ? <li key={item.id} className="thread-aux"><div className="choices" role="group" aria-label={item.question || "Quick replies"}>{item.choices.map(choice => <button key={choice.value} className="chip" onClick={() => onChoice(choice.value)}>{choice.label}</button>)}</div></li> : null;
      return null;
    })}
    {thinking ? <li className="thread-aux"><ThinkingRow label={thinking}/></li> : null}
  </ol>;
}
