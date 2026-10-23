"""Make a realistic long Persian talk for testing long-video discovery.

Text: written by the creative model, one topic per section, in spoken Persian (a coach talking to an audience, or an interview between two people).
Speech: edge-tts voices (real synthetic speech, not a mock). Pauses and a mixed Persian/English section can be added.
Video: a quiet animated waveform so the file is a normal 16:9 mp4.

    python scripts/make_test_talk.py out.mp4 --minutes 10 [--interview] [--english-terms] [--pauses]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

TOPICS = [
    "سه اشتباه رایج در راه‌اندازی کسب‌وکار آنلاین و چرا فروش رشد نمی‌کند",
    "چطور قیمت‌گذاری محصول را درست انجام بدهیم و از جنگ قیمت دور بمانیم",
    "داستان یک شکست بزرگ در کسب‌وکار و درسی که از آن گرفتم",
    "چطور اولین تیم کوچک را استخدام کنیم و نیروی خوب را نگه داریم",
    "بهره‌وری شخصی: چرا برنامه‌ریزی روزانه معمولاً شکست می‌خورد و چه جایگزینی دارد",
    "اعتماد مشتری: یک مثال واقعی از اینکه صداقت چطور فروش را بالا برد",
    "تبلیغات اینستاگرام: چه چیزهایی کار می‌کند و چه چیزهایی پول سوزاندن است",
    "یک باور اشتباه دربارهٔ موفقیت که مردم را سال‌ها عقب نگه می‌دارد",
    "چطور با مشتری ناراضی حرف بزنیم و او را به طرفدار تبدیل کنیم",
    "هفت دقیقه اول صبح: عادت‌هایی که تمرکز را کل روز حفظ می‌کند",
    "سرمایه‌گذاری روی مهارت یا روی ابزار؟ یک بحث تند و صریح",
    "چگونه از یک ایدهٔ ساده در سه ماه اولین درآمد را ساختم",
]


def ask_text(topic: str, words: int, interview: bool, english: bool) -> str:
    from creative import llm
    from pydantic import BaseModel

    class Out(BaseModel):
        text: str

    style = ("یک مصاحبه بین دو نفر: هر خط با «الف:» (مصاحبه‌گر) یا «ب:» (مهمان) شروع شود." if interview else
             "تک‌گویی یک مربی با مخاطبش؛ بدون عنوان و بدون فهرست.")
    mix = " چند اصطلاح انگلیسی مثل MVP، churn rate و landing page را همان‌طور که در گفتار فارسی گفته می‌شود وسط جمله‌ها بیاور." if english else ""
    result = llm.ask(Out, "You write natural spoken Persian for a talk or podcast. Return JSON {\"text\": \"...\"}. No markdown, no stage directions.",
                     f"موضوع: {topic}\nحدود {words} کلمه، محاوره‌ای و طبیعی، با مثال و جملهٔ تأثیرگذار، شروع قوی و پایان مشخص. {style}{mix}",
                     route=llm.DIRECTOR_ROUTE, tokens=4500, attempts=3)
    return result.text.strip()


async def speak(text: str, voice: str, path: Path) -> None:
    import edge_tts
    for attempt in range(8):                      # the speech service is reached over a flaky link: retry with a growing pause
        try:
            await asyncio.wait_for(edge_tts.Communicate(text, voice, rate="+0%").save(str(path)), 120)
            return
        except Exception as exc:
            print(f"tts retry {attempt + 1}: {type(exc).__name__}", flush=True)
            await asyncio.sleep(min(60, 5 * (attempt + 1)))
    raise RuntimeError("speech service unreachable")


def duration(path: Path) -> float:
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    return float(out.decode().strip())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--minutes", type=float, default=10)
    parser.add_argument("--interview", action="store_true")
    parser.add_argument("--english-terms", action="store_true")
    parser.add_argument("--pauses", action="store_true")
    parser.add_argument("--cache", help="folder that keeps the written text and the speech, so a failed run resumes instead of starting over")
    args = parser.parse_args()
    target = args.minutes * 60
    work = Path(args.cache) if args.cache else Path(tempfile.mkdtemp(prefix="talk-"))
    work.mkdir(parents=True, exist_ok=True)
    parts, total, index = [], 0.0, 0
    voices = {"الف": "fa-IR-DilaraNeural", "ب": "fa-IR-FaridNeural"}
    while total < target:
        topic = TOPICS[index % len(TOPICS)]
        text_file = work / f"text{index:03d}.txt"
        if text_file.is_file():
            text = text_file.read_text()
        else:
            text = ask_text(topic, 260, args.interview, args.english_terms and index % 3 == 1)
            text_file.write_text(text)
        lines = []
        if args.interview:
            for raw in text.splitlines():
                raw = raw.strip()
                if ":" in raw and raw.split(":", 1)[0].strip() in voices:
                    who, said = raw.split(":", 1)
                    lines.append((voices[who.strip()], said.strip()))
                elif raw:
                    lines.append((voices["ب"], raw))
        else:
            lines = [("fa-IR-FaridNeural", text)]
        for voice, said in lines:
            if not said:
                continue
            path = work / f"p{len(parts):04d}.mp3"
            if not path.is_file() or path.stat().st_size < 1000:
                asyncio.run(speak(said, voice, path))
            parts.append(path)
            total += duration(path)
            if args.pauses:
                gap = work / f"g{len(parts):04d}.mp3"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "4.5", "-q:a", "9", str(gap)], check=True)
                parts.append(gap)
                total += 4.5
        index += 1
        print(f"{index} sections, {total / 60:.1f} min", flush=True)
    listing = work / "list.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts))
    audio = work / "all.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c:a", "libmp3lame", "-q:a", "4", str(audio)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(audio), "-filter_complex",
                    "[0:a]showwaves=s=640x360:mode=cline:colors=0xf5b800:rate=12,format=yuv420p[v]", "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "30", "-c:a", "aac", "-b:a", "96k", "-shortest", args.out], check=True)
    print(json.dumps({"out": args.out, "seconds": round(duration(Path(args.out)), 1)}))


if __name__ == "__main__":
    main()
