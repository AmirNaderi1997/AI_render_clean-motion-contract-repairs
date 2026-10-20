import React from "react";
import { Link } from "react-router-dom";
import { Icon, IconName } from "./components/Icon";

const features: { icon: IconName; title: string; desc: string }[] = [
  { icon: "paperclip", title: "Start with footage", desc: "Add a video, images or a product link, or just describe what you need." },
  { icon: "spark", title: "Talk to your editor", desc: "Plan, change and refine the edit in a conversation." },
  { icon: "film", title: "Watch it come together", desc: "Follow progress, preview the result and download the final video." },
  { icon: "captions", title: "Persian and English", desc: "Captions, dubbing and voice-over that respect both languages." },
];

export default function Landing() {
  return <div className="landing">
    <header className="landing-top"><Link to="/studio" className="brand"><span className="brand-mark"><Icon name="spark" size={18}/></span><span className="brand-name">EditorGPT</span></Link>
      <nav className="landing-nav"><Link className="btn btn-sm btn-ghost" to="/login">Log in</Link><Link className="btn btn-sm" to="/signup">Sign up</Link></nav></header>
    <main id="main-content" className="landing-main">
      <h1>Create videos by talking to an AI editor</h1>
      <p>Upload footage or start with a prompt. Plan, edit, render and review your video in one conversation.</p>
      <div className="landing-cta"><Link className="btn btn-lg" to="/signup">Create your first video</Link><Link className="btn btn-lg btn-secondary" to="/studio">Try the editor</Link></div>
      <ul className="landing-features">{features.map(item => <li key={item.title}><span className="empty-icon"><Icon name={item.icon} size={20}/></span><b>{item.title}</b><span>{item.desc}</span></li>)}</ul>
    </main>
  </div>;
}
