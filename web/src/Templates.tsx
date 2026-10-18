import { useNavigate } from "react-router-dom";
import { Icon } from "./EditorShell";

const templates = [
  { id: "talking", title: "Talking Head", description: "Captions, smart zooms, key moments and polished social pacing.", prompt: "این ویدیوی صحبتی را مثل یک ریلز حرفه‌ای اینستاگرام تدوین کن" },
  { id: "reel", title: "Instagram Reel", description: "Turn raw footage into an engaging vertical edit.", prompt: "از این ویدیو یک ریلز جذاب اینستاگرامی بساز" },
  { id: "localize", title: "Video Localization", description: "Persian dubbing and captions, aligned to the original video.", prompt: "این ویدیو را با دوبله و زیرنویس فارسی آماده کن" },
  { id: "product", title: "Product Commercial", description: "Build a product story from a URL, photos or a written brief.", prompt: "برای این محصول یک تیزر موشن ۳۰ ثانیه‌ای با نریشن فارسی بساز" },
  { id: "dropshipping", title: "Dropshipping Ad", description: "Localize product tutorials while preserving their visual rhythm.", prompt: "این ویدیوی محصول را برای فروش فارسی‌سازی کن" },
  { id: "podcast", title: "Podcast Clips", description: "Find the strongest moments and turn them into short clips.", prompt: "بهترین بخش‌های این پادکست را به کلیپ کوتاه تبدیل کن" },
  { id: "captions", title: "Auto Captions", description: "Add readable, timed Persian or English captions.", prompt: "برای این ویدیو زیرنویس خوانا و حرفه‌ای بساز" },
  { id: "documentary", title: "Documentary", description: "Shape footage, narration and supporting visuals into a story.", prompt: "از این محتوا یک ویدیوی مستند کوتاه و منسجم بساز" },
];

export default function Templates() {
  const navigate = useNavigate();
  return <div className="eg-page" dir="auto">
    <header className="eg-page-header"><span className="eg-eyebrow">Start with a workflow</span><h1>Templates</h1><p>Templates guide the assistant. You can change every decision through the conversation.</p></header>
    <div className="eg-template-grid">{templates.map(template => <button key={template.id} className="eg-template-card" onClick={() => navigate(`/studio?template=${template.id}&prompt=${encodeURIComponent(template.prompt)}`)}>
      <span className="eg-template-icon"><Icon name="spark"/></span><span><b>{template.title}</b><small>{template.description}</small></span><Icon name="chevron" size={18}/>
    </button>)}</div>
  </div>;
}
