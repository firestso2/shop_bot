import re


def is_numbered_text(content: str) -> bool:
    return bool(re.match(r'^\s*1\.', content.strip()))


def parse_numbered_block(full_text: str, index: int) -> str | None:
    pattern = re.compile(r'(?m)^\s*(\d+)\.\s*')
    matches = list(pattern.finditer(full_text))
    if not matches:
        return full_text.strip()
    for i, match in enumerate(matches):
        if int(match.group(1)) != index:
            continue
        content_start = match.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        return full_text[content_start:content_end].rstrip('\n').rstrip()
    return None


def get_block_for_delivery(content: str, delivery_index: int) -> str:
    if is_numbered_text(content):
        block = parse_numbered_block(content, delivery_index)
        return block if block else content
    return content


def _parse_raw_links(text: str) -> list[str]:
    lines = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if line[0].isdigit():
            parts = line.split(None, 1)
            if len(parts) == 2:
                prefix = parts[0].rstrip('.)')
                if prefix.isdigit():
                    line = parts[1].strip()
        if line:
            lines.append(line)
    return lines
