"""Deterministic Markdown shape checks, separate from narrative semantics."""

from __future__ import annotations

_REPORT_MARKDOWN_H2S = (
    "## Key Takeaway",
    "## 시장 현황",
    "## 중장기 맥락",
    "## 주요 지표들",
    "## 지켜봐야 할 것들",
    "## 관심을 가져볼 만한 이슈들",
    "## 출처·데이터 안내",
)


def _report_section_lines(value: str) -> dict[str, tuple[str, ...]]:
    """Return visible block-level lines for each approved Report H2 section."""

    sections: dict[str, list[str]] = {heading: [] for heading in _REPORT_MARKDOWN_H2S}
    current: str | None = None
    fence: tuple[str, int] | None = None

    for line in value.splitlines():
        content = _markdown_block_content(line)
        if content is None:
            if (
                current is not None
                and sections[current]
                and sections[current][-1] != ""
            ):
                sections[current].append("")
            continue

        if fence is not None:
            candidate = _fence_run(content)
            if (
                candidate is not None
                and candidate[0] == fence[0]
                and candidate[1] >= fence[1]
                and not candidate[2].strip(" \t")
            ):
                fence = None
                if (
                    current is not None
                    and sections[current]
                    and sections[current][-1] != ""
                ):
                    sections[current].append("")
            continue

        candidate = _fence_run(content)
        if candidate is not None and not (candidate[0] == "`" and "`" in candidate[2]):
            fence = candidate[0], candidate[1]
            if (
                current is not None
                and sections[current]
                and sections[current][-1] != ""
            ):
                sections[current].append("")
            continue

        heading = content.rstrip()
        if heading in sections:
            current = heading
            continue
        if current is not None:
            sections[current].append(content.rstrip())

    return {heading: tuple(lines) for heading, lines in sections.items()}


def _markdown_list_item(line: str) -> tuple[str, str] | None:
    """Classify one visible CommonMark block-level list marker."""

    if len(line) >= 2 and line[0] in "-+*" and line[1] in " \t":
        return "unordered", line[2:].strip()

    index = 0
    while index < len(line) and line[index].isdigit():
        index += 1
    if (
        1 <= index <= 9
        and index + 1 < len(line)
        and line[index] in ".)"
        and line[index + 1] in " \t"
    ):
        return "ordered", line[index + 2 :].strip()
    return None


def _validate_key_takeaway(
    lines: tuple[str, ...], *, field_label: str, errors: list[str]
) -> None:
    visible = [line for line in lines if line.strip()]
    items = [_markdown_list_item(line) for line in visible]
    if not 3 <= len(items) <= 5 or any(
        item is None or item[0] != "unordered" or not item[1] for item in items
    ):
        errors.append(
            f"{field_label} Key Takeaway must contain 3 to 5 nonempty unordered list items"
        )


def _prose_paragraph_count(lines: tuple[str, ...]) -> int:
    count = 0
    inside_paragraph = False
    for line in lines:
        if line.strip():
            if not inside_paragraph:
                count += 1
                inside_paragraph = True
        else:
            inside_paragraph = False
    return count


def _validate_narrative_section(
    lines: tuple[str, ...],
    *,
    heading: str,
    report_type: str,
    minimum: int,
    field_label: str,
    errors: list[str],
) -> None:
    section_name = heading.removeprefix("## ")
    visible = [line for line in lines if line.strip()]
    has_nonprose_block = any(
        _markdown_list_item(line) is not None or line.lstrip().startswith("#")
        for line in visible
    )
    if has_nonprose_block:
        errors.append(
            f"{field_label} {section_name} must use prose paragraphs without top-level lists or headings"
        )
        return

    paragraph_count = _prose_paragraph_count(lines)
    if paragraph_count < minimum:
        errors.append(
            f"{field_label} {section_name} must contain at least {minimum} prose paragraphs for {report_type}"
        )


def _markdown_headings(value: str) -> tuple[str, ...]:
    headings: list[str] = []
    fence: tuple[str, int] | None = None
    for line in value.splitlines():
        content = _markdown_block_content(line)
        if content is None:
            continue

        if fence is not None:
            candidate = _fence_run(content)
            if (
                candidate is not None
                and candidate[0] == fence[0]
                and candidate[1] >= fence[1]
                and not candidate[2].strip(" \t")
            ):
                fence = None
            continue

        candidate = _fence_run(content)
        if candidate is not None and not (candidate[0] == "`" and "`" in candidate[2]):
            fence = candidate[0], candidate[1]
            continue

        heading = content.rstrip()
        prefix, separator, _ = heading.partition(" ")
        if separator and 1 <= len(prefix) <= 6 and set(prefix) == {"#"}:
            headings.append(heading)
    return tuple(headings)


def _markdown_block_content(line: str) -> str | None:
    """Return content at CommonMark block indentation, or ignore code indentation."""

    column = 0
    offset = 0
    while offset < len(line) and line[offset] in (" ", "\t"):
        if line[offset] == " ":
            column += 1
        else:
            column += 4 - (column % 4)
        offset += 1
        if column > 3:
            return None
    return line[offset:]


def _fence_run(content: str) -> tuple[str, int, str] | None:
    """Return a possible fenced-code marker character, width, and remainder."""

    if not content or content[0] not in ("`", "~"):
        return None
    marker = content[0]
    width = 0
    while width < len(content) and content[width] == marker:
        width += 1
    if width < 3:
        return None
    return marker, width, content[width:]
