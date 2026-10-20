import type { IconName } from "./components/Icon";

export interface TemplateDef { id: string; title: string; description: string; prompt: string; category: "Social" | "Commercial" | "Localization" | "Long form"; format: string; icon: IconName }

/** Templates only pre-fill the Studio prompt; the assistant and backend decide what is supported. */
export const templates: TemplateDef[] = [
  { id: "talking", title: "Talking Head", description: "Captions, smart zooms, key moments and polished social pacing.", prompt: "این ویدیوی صحبتی را مثل یک ریلز حرفه‌ای اینستاگرام تدوین کن", category: "Social", format: "Vertical 9:16", icon: "mic2" },
  { id: "reel", title: "Instagram Reel", description: "Turn raw footage into an engaging vertical edit.", prompt: "از این ویدیو یک ریلز جذاب اینستاگرامی بساز", category: "Social", format: "Vertical 9:16", icon: "film" },
  { id: "localize", title: "Video Localization", description: "Persian dubbing and captions, aligned to the original video.", prompt: "این ویدیو را با دوبله و زیرنویس فارسی آماده کن", category: "Localization", format: "Any ratio", icon: "globe" },
  { id: "product", title: "Product Commercial", description: "Build a product story from a URL, photos or a written brief.", prompt: "برای این محصول یک تیزر موشن ۳۰ ثانیه‌ای با نریشن فارسی بساز", category: "Commercial", format: "Vertical 9:16", icon: "wand" },
  { id: "dropshipping", title: "Dropshipping Ad", description: "Localize product tutorials while preserving their visual rhythm.", prompt: "این ویدیوی محصول را برای فروش فارسی‌سازی کن", category: "Commercial", format: "Vertical 9:16", icon: "video" },
  { id: "podcast", title: "Podcast Clips", description: "Find the strongest moments and turn them into short clips.", prompt: "بهترین بخش‌های این پادکست را به کلیپ کوتاه تبدیل کن", category: "Long form", format: "Short clips", icon: "mic" },
  { id: "captions", title: "Auto Captions", description: "Add readable, timed Persian or English captions.", prompt: "برای این ویدیو زیرنویس خوانا و حرفه‌ای بساز", category: "Social", format: "Any ratio", icon: "captions" },
  { id: "documentary", title: "Documentary", description: "Shape footage, narration and supporting visuals into a story.", prompt: "از این محتوا یک ویدیوی مستند کوتاه و منسجم بساز", category: "Long form", format: "Horizontal 16:9", icon: "image" },
];
export const templatePrompts: Record<string, string> = Object.fromEntries(templates.map(item => [item.id, item.prompt]));
export const suggestions = ["Edit an Instagram Reel", "Remove pauses and mistakes", "Add engaging Persian captions", "Create a product advertisement"];
