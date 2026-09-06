"""Development-led reading order, independent of creation and alignment."""

def reading_blocks(document):
    ordered = []
    neighbors = {}
    for relation in document["relations"]:
        source, target = relation["from_block_id"], relation["to_block_id"]
        neighbors.setdefault(source, set()).add(target)
        neighbors.setdefault(target, set()).add(source)

    def position(block):
        value = (block.get("layout") or {}).get("position_y")
        return (value if isinstance(value, (int, float)) else block.get("reading_order", 0) * 14.4, block.get("reading_order", 0))

    for section in sorted(document["sections"], key=lambda item: item["order"]):
        blocks = [b for b in document["blocks"] if b["section_id"] == section["id"]]
        cues = sorted((b for b in blocks if b["lane"] == "left"), key=position)
        developments = sorted((b for b in blocks if b["lane"] == "right"), key=position)
        emitted = set()
        for development in developments:
            for cue in cues:
                if cue["id"] not in emitted and development["id"] in neighbors.get(cue["id"], set()):
                    ordered.append(cue)
                    emitted.add(cue["id"])
            ordered.append(development)
        ordered.extend(cue for cue in cues if cue["id"] not in emitted)
    return ordered


def render_sections(document, render_block):
    lines = []
    sequence = reading_blocks(document)
    for section in sorted(document["sections"], key=lambda item: item["order"]):
        blocks = [b for b in sequence if b["section_id"] == section["id"]]
        if not blocks:
            continue
        lines.append("# " + section["title"])
        development_ids = {b["id"] for b in blocks if b["lane"] == "right"}
        linked = set()
        for relation in document["relations"]:
            source, target = relation["from_block_id"], relation["to_block_id"]
            if source in development_ids:
                linked.add(target)
            if target in development_ids:
                linked.add(source)
        divider = False
        for block in blocks:
            rendered = render_block(block)
            if not rendered:
                continue
            if block["lane"] == "left" and block["id"] not in linked and not divider:
                lines.append("---")
                divider = True
            lines.append(rendered)
    return lines
