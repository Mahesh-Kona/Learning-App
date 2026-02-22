import re

BLOCK_TAGS = {'q', 'def', 'take', 'imp', 'mem', 'ex', 'diff'}
INLINE_TAGS = {'b', 'i', 'u', 'hl', 'h', 'sh', 'li', 'nli'}

def parse_inline_spans(text):
    """Parse inline tags into spans list."""
    spans = []
    pattern = re.compile(r'\[\[(\w+)\]\](.*?)\[\[\/\1\]\]', re.DOTALL)
    last_end = 0

    for match in pattern.finditer(text):
        # Normal text before tag
        if match.start() > last_end:
            normal = text[last_end:match.start()]
            if normal:
                spans.append({"text": normal, "tag": "normal"})

        tag = match.group(1)
        content = match.group(2)

        if tag in INLINE_TAGS:
            spans.append({"text": content, "tag": tag})
        else:
            # Unknown tag — treat as normal
            spans.append({"text": content, "tag": "normal"})

        last_end = match.end()

    # Remaining text
    if last_end < len(text):
        remaining = text[last_end:]
        if remaining:
            spans.append({"text": remaining, "tag": "normal"})

    return spans if spans else [{"text": text, "tag": "normal"}]


def parse_raw_text(raw_text):
    """
    Split raw_text into a list of output blocks.
    Block tags become type=block, rest becomes type=text with spans.
    """
    output = []

    # Pattern to find block-level tags
    block_pattern = re.compile(
        r'\[\[(q|def|take|imp|mem|ex|diff)\]\]([\s\S]*?)\[\[\/\1\]\]',
        re.DOTALL
    )

    last_end = 0

    for match in block_pattern.finditer(raw_text):
        # Text before this block tag
        before = raw_text[last_end:match.start()].strip()
        if before:
            # Could have multiple lines — split by newline
            for line in before.split('\n'):
                line = line.strip()
                if line:
                    output.append({
                        "type": "text",
                        "spans": parse_inline_spans(line)
                    })

        tag = match.group(1)
        content = match.group(2).strip()

        output.append({
            "type": "block",
            "block_type": tag,
            "spans": parse_inline_spans(content)
        })

        last_end = match.end()

    # Remaining text after last block tag
    remaining = raw_text[last_end:].strip()
    if remaining:
        for line in remaining.split('\n'):
            line = line.strip()
            if line:
                output.append({
                    "type": "text",
                    "spans": parse_inline_spans(line)
                })

    return output


def parse_blocks(data_json):
    """Entry point — process data_json blocks from DB.

    Supports both legacy schemas (list of blocks) and the newer
    ``{"blocks": [...]}`` wrapper used by the web editor.
    """
    # Normalise to a list of blocks
    if isinstance(data_json, dict):
        blocks = data_json.get("blocks") or []
    elif isinstance(data_json, list):
        blocks = data_json
    else:
        blocks = []

    output = []
    for block in blocks:
        if not isinstance(block, dict):
            # Unknown structure; skip safely
            continue

        btype = block.get("type")
        if btype == "text":
            # New schema stores raw tagged text under "text";
            # fall back to legacy "value" if present.
            raw = block.get("text") or block.get("value") or ""
            parsed = parse_raw_text(raw)
            output.extend(parsed)
        else:
            # image, keypoints, divider etc. — pass through as-is
            output.append(block)

    return output