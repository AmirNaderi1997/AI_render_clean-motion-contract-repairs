"""Thread-safe per-render typography; never mutate shared style module globals."""

def caption_font(ass: str, settings: dict) -> str:
    if settings.get('caption_font') != 'Vazirmatn': return ass
    lines = []
    for line in ass.splitlines():
        if line.startswith('Style: '):
            fields = line.split(',')
            if fields[0].removeprefix('Style: ') in {'caption', 'key', 'lead', 'cap'}:
                fields[1] = 'Vazirmatn'
                line = ','.join(fields)
        lines.append(line)
    return '\n'.join(lines) + '\n'
