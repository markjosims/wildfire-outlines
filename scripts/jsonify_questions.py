"""
Read questions stored in Markdown files and serialize them as JSON files
for easy loading into an LLM.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Dict, Optional, Any

questions_a = Path("./wildfire_questions_A.md")
questions_b = Path("./wildfire_questions_B.md")

CHAPTER_REGEX = re.compile(
    r"(?m)^\s*\*\*CHAPTER\s+(?P<chapter>\d+)(?::\s*|\s+)?(?P<title>.*?)\*\*\s*$"
)

QUESTION_A_HEADER_REGEX = re.compile(
    r"(?m)^\s*(?:\*\*)?\s*\\?\[CONCEPT:.*?DIFFICULTY:.*$"
)
QUESTION_A_METADATA_REGEX = re.compile(
    r"\[CONCEPT:\s*(?P<concept_description>.*?)\s*\]\s*\[DIFFICULTY:\s*(?P<difficulty>.*?)\s*\]"
)
QUESTION_B_SPLIT_REGEX = re.compile(r"(?m)^\s*---\s*$")
QUESTION_B_HEADER_REGEX = re.compile(
    r"^\s*(?:#{3,4}\s*)?(?:\*\*(?P<bold_header>.+?)\*\*|(?P<plain_header>[^\n*][^\n]*))\s*$",
    re.MULTILINE,
)
FORMAT_LABEL_REGEX = re.compile(
    r"(?im)^\s*(?:\*{0,2}Format[^\\n]*\*{0,2}|\*Format[^\\n]*\*)\s*$"
)
QUESTION_LABEL_REGEX = re.compile(
    r"(?im)^\s*\*{0,2}(?:Question|Scenario)(?:\s*\([^)\n]+\))?:?\*{0,2}\s*"
)
ANSWER_LABEL_REGEX = re.compile(r"(?im)^\s*\*{0,2}Answer:?\*{0,2}\s*")
EXPLANATION_LABEL_REGEX = re.compile(
    r"(?im)^\s*\*{0,2}(?:Instructional explanation|Explanation(?:\s*&\s*steps)?):?\*{0,2}\s*"
)


def clean_field(text: str) -> str:
    return text.strip().replace("\r\n", "\n")


def clean_inline_markup(text: str) -> str:
    text = text.replace("\\[", "[").replace("\\]", "]").replace("\\!", "!")
    text = text.replace("\\.", ".").replace("\\_", "_")
    text = re.sub(r"^\s*#+\s*", "", text)
    text = text.replace("**", "").replace("*", "").replace("__", "").replace("`", "")
    return clean_field(text)


def trim_chapter_divider(text: str) -> str:
    lines = text.splitlines()
    while lines:
        stripped = lines[-1].strip().replace("*", "").replace("\\_", "")
        if stripped and stripped != "_":
            break
        lines.pop()
    return clean_field("\n".join(lines))


def split_chapters(content: str) -> List[Dict[str, str]]:
    matches = list(CHAPTER_REGEX.finditer(content))
    chapters: List[Dict[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        chapters.append(
            {
                "chapter": match.group("chapter"),
                "title": clean_field(match.group("title")),
                "text": content[start:end].strip(),
            }
        )
    return chapters


def parse_questions_a(chapter_text: str) -> List[Dict[str, str]]:
    headers = list(QUESTION_A_HEADER_REGEX.finditer(chapter_text))
    questions = []
    for index, match in enumerate(headers):
        start = match.start()
        end = (
            headers[index + 1].start()
            if index + 1 < len(headers)
            else len(chapter_text)
        )
        block = chapter_text[start:end].strip()

        header_line = match.group(0)
        normalized_header = clean_inline_markup(header_line)
        metadata = QUESTION_A_METADATA_REGEX.search(normalized_header)
        if not metadata:
            raise ValueError(f"Could not parse concept header: {header_line!r}")

        question_match = re.search(
            r"(?ms)^\s*\*{0,2}QUESTION:\*{0,2}\s*(?P<question_text>.*?)(?=^\s*\*{0,2}Answer:\*{0,2}\s*)",
            block,
        )
        answer_match = re.search(
            r"(?ms)^\s*\*{0,2}Answer:\*{0,2}\s*(?P<answer>.*)\s*$",
            block,
        )
        if not question_match or not answer_match:
            raise ValueError(f"Could not parse question block in A: {block[:160]!r}")

        questions.append(
            {
                "concept_description": clean_field(
                    metadata.group("concept_description")
                ),
                "difficulty": clean_field(metadata.group("difficulty")),
                "question_text": clean_field(question_match.group("question_text")),
                "answer": clean_field(answer_match.group("answer")),
            }
        )

    return questions


def split_b_blocks(chapter_text: str) -> List[str]:
    return [
        block.strip()
        for block in QUESTION_B_SPLIT_REGEX.split(chapter_text)
        if block.strip() and "___" not in block
    ]


def parse_questions_b(chapter_text: str) -> List[Dict[str, str]]:
    questions = []
    for block in split_b_blocks(chapter_text):
        header_match = QUESTION_B_HEADER_REGEX.search(block)
        if not header_match:
            continue

        header = clean_inline_markup(
            header_match.group("bold_header")
            or header_match.group("plain_header")
            or ""
        )
        remainder = block[header_match.end() :].strip()

        lines = remainder.splitlines()
        format_line = ""
        while lines and not lines[0].strip():
            lines.pop(0)
        if lines and FORMAT_LABEL_REGEX.match(lines[0]):
            format_line = clean_inline_markup(lines.pop(0))

        remainder = "\n".join(lines).strip()
        answer_match = ANSWER_LABEL_REGEX.search(remainder)
        if not answer_match:
            raise ValueError(f"Could not locate answer block in B: {block[:160]!r}")

        question_portion = remainder[: answer_match.start()].strip()
        answer_portion = remainder[answer_match.end() :].strip()

        question_portion = QUESTION_LABEL_REGEX.sub(
            "", question_portion, count=1
        ).strip()

        if not format_line:
            question_lines = [
                line for line in question_portion.splitlines() if line.strip()
            ]
            if len(question_lines) > 1:
                first_line = clean_inline_markup(question_lines[0])
                if len(first_line) <= 80 and "?" not in first_line:
                    format_line = first_line
                    question_portion = "\n".join(question_lines[1:]).strip()

        explanation_match = EXPLANATION_LABEL_REGEX.search(answer_portion)
        if explanation_match:
            answer_text = answer_portion[: explanation_match.start()].strip()
            explanation_text = answer_portion[explanation_match.end() :].strip()
        else:
            answer_text = answer_portion.strip()
            explanation_text = ""

        concept_match = re.match(
            r"(?i)(?P<item_type>assessment item|concept|item)?\s*(?P<concept_num>\d+)\.?\s*(?:[–-]\s*|\s{2,})?(?P<concept_description>.*)",
            header,
        )
        if concept_match:
            concept_num = concept_match.group("concept_num")
            concept_description = clean_field(
                concept_match.group("concept_description")
            )
            item_type = clean_field(concept_match.group("item_type") or "")
        else:
            concept_num = ""
            concept_description = header
            item_type = ""

        questions.append(
            {
                "item_type": item_type,
                "concept_num": concept_num,
                "concept_description": concept_description,
                "question_format": format_line,
                "question_text": clean_field(question_portion),
                "answer": clean_inline_markup(answer_text),
                "explanation_text": trim_chapter_divider(explanation_text),
            }
        )

    return questions


def write_json(markdown_path: Path, parser) -> List[Dict[str, Any]]:
    content = markdown_path.read_text()
    json_data = []
    for chapter in split_chapters(content):
        json_data.append(
            {
                "chapter": chapter["chapter"],
                "title": chapter["title"],
                "questions": parser(chapter["text"]),
            }
        )

    output_path = markdown_path.with_suffix(".json")
    output_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False) + "\n")
    return json_data


if __name__ == "__main__":
    json_a = write_json(questions_a, parse_questions_a)
    json_b = write_json(questions_b, parse_questions_b)
    print(
        f"Wrote {questions_a.with_suffix('.json')} ({sum(len(chapter['questions']) for chapter in json_a)} questions)"
    )
    print(
        f"Wrote {questions_b.with_suffix('.json')} ({sum(len(chapter['questions']) for chapter in json_b)} questions)"
    )
