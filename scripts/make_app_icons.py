"""Deterministic code-native application glyph; no network or generated artwork."""
from pathlib import Path
from PIL import Image, ImageDraw
root = Path(__file__).resolve().parents[1] / 'web/public/icons'
root.mkdir(parents=True, exist_ok=True)
for name, size in [('app-192.png',192),('app-512.png',512),('apple-touch-icon.png',180)]:
    image=Image.new('RGB',(size,size),'#101010')
    draw=ImageDraw.Draw(image)
    points=[(.5,.20),(.58,.42),(.80,.5),(.58,.58),(.5,.80),(.42,.58),(.20,.5),(.42,.42)]
    draw.polygon([(int(x*size),int(y*size)) for x,y in points],fill='#f3f3f3')
    image.save(root/name)
