from __future__ import annotations

import json
import math
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup, Tag


DEFAULT_RETRIEVAL_QUERIES = [
    "县域生产性经济的特色产业、优势产业、新兴产业及发展目标、方向和重点项目；不包括教育、医疗、社会保障、城市建设等公共服务",
    "特色产业发展重大工程、优势产业发展重大工程、新兴产业重大工程专栏表格",
    "制造业、现代农业、文旅康养、新材料、低空经济、新型储能等产业体系和产业链规划",
]

NON_INDUSTRY_SUMMARY_TERMS = (
    "基础设施",
    "特色乡镇",
    "城市更新",
    "教育产业",
    "医疗产业",
    "社会保障",
    "乡村振兴",
)


@dataclass(frozen=True)
class TextChunk:
    chunk_id: str
    text: str
    kind: str


def load_env_file(path: Path) -> None:
    """Load a small .env file without overwriting process-level configuration."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def fetch_html(url: str, timeout: int = 60) -> str:
    response = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "Mozilla/5.0 (compatible; CountyPolicyProfile/0.1)"},
    )
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _blocks_to_chunks(blocks: list[tuple[str, str]]) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    paragraph_buffer: list[str] = []
    paragraph_chars = 0

    def flush_paragraphs() -> None:
        nonlocal paragraph_buffer, paragraph_chars
        if paragraph_buffer:
            chunks.append(
                TextChunk(
                    chunk_id=f"chunk-{len(chunks) + 1:03d}",
                    text="\n".join(paragraph_buffer),
                    kind="paragraph",
                )
            )
        paragraph_buffer = []
        paragraph_chars = 0

    for kind, text in blocks:
        if kind == "table":
            flush_paragraphs()
            chunks.append(TextChunk(f"chunk-{len(chunks) + 1:03d}", text, "table"))
            continue
        if paragraph_buffer and paragraph_chars + len(text) > 1800:
            flush_paragraphs()
        paragraph_buffer.append(text)
        paragraph_chars += len(text)
    flush_paragraphs()
    return chunks


def extract_article(html: str) -> tuple[str, list[TextChunk]]:
    """Extract paragraph groups and intact HTML tables from a government article."""
    soup = BeautifulSoup(html, "lxml")
    title_node = soup.select_one(".article_title") or soup.find("title")
    title = _clean(title_node.get_text(" ", strip=True)) if title_node else ""
    article = soup.select_one(".article_content")
    if article is None:
        raise ValueError("未找到文字版正文容器 .article_content")

    blocks: list[tuple[str, str]] = []
    for node in article.find_all(["p", "table"]):
        if not isinstance(node, Tag):
            continue
        if node.name == "p" and node.find_parent("table") is not None:
            continue
        if node.name == "table":
            rows = []
            for row in node.find_all("tr"):
                cells = [_clean(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
                cells = [cell for cell in cells if cell]
                if cells:
                    rows.append(" | ".join(cells))
            text = "\n".join(rows)
            if text:
                blocks.append(("table", text))
        else:
            text = _clean(node.get_text(" ", strip=True))
            if text:
                blocks.append(("paragraph", text))

    return title, _blocks_to_chunks(blocks)


def extract_docx(path: Path) -> tuple[str, list[TextChunk]]:
    """Extract paragraphs and tables in document order from a converted legacy Word file."""
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    body = root.find(f"{namespace}body")
    if body is None:
        raise ValueError("DOCX缺少正文")

    blocks: list[tuple[str, str]] = []

    def node_text(node: ET.Element) -> str:
        return _clean("".join(text.text or "" for text in node.iter(f"{namespace}t")))

    for child in body:
        if child.tag == f"{namespace}p":
            text = node_text(child)
            if text:
                blocks.append(("paragraph", text))
        elif child.tag == f"{namespace}tbl":
            rows = []
            for row in child.findall(f".//{namespace}tr"):
                cells = [node_text(cell) for cell in row.findall(f"{namespace}tc")]
                cells = [cell for cell in cells if cell]
                if cells:
                    rows.append(" | ".join(cells))
            if rows:
                blocks.append(("table", "\n".join(rows)))

    title = next((text for kind, text in blocks if kind == "paragraph"), path.stem)
    return title, _blocks_to_chunks(blocks)


class DashScopeClient:
    def __init__(self, api_key: str, base_url: str, chat_model: str, embedding_model: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        )

    def embeddings(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), 10):
            response = self.session.post(
                f"{self.base_url}/embeddings",
                json={
                    "model": self.embedding_model,
                    "input": texts[start : start + 10],
                    "dimensions": 1024,
                    "encoding_format": "float",
                },
                timeout=90,
            )
            response.raise_for_status()
            data = sorted(response.json()["data"], key=lambda item: item["index"])
            vectors.extend(item["embedding"] for item in data)
        return vectors

    def extract_profile(
        self, context: str, county: str, title: str, url: str, plan_period: str = "2026-2030"
    ) -> dict:
        schema = {
            "industries": [
                {
                    "county": county,
                    "industry": "标准产业名称",
                    "parent_industry": None,
                    "industry_aliases": [],
                    "development_goal": "",
                    "development_directions": [],
                    "planned_actions": [],
                    "planned_projects": [],
                    "mentioned_in_plan": True,
                    "specific_policy_found": None,
                    "source_document": title,
                    "source_url": url,
                    "plan_period": plan_period,
                    "evidence": [{"chunk_id": "chunk-001", "quote": "原文短句"}],
                }
            ]
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "你是县域产业规划信息抽取器。只根据给定切片提取，禁止补充常识。"
                    "这里只建立生产性经济产业画像，排除教育、医疗、社会保障、城市更新、"
                    "一般基础设施、乡村治理等公共服务板块。"
                    "每个明确产业生成一条记录；优先采用专栏表格第一列或章节明确命名的产业，"
                    "若发展目标明确列举重点子产业或特色产业名片，也为每个子产业生成一条记录，"
                    "并填写 parent_industry；例如现代农业下明确列举的竹应生成竹产业记录。"
                    "必须逐项展开“做强A、B、C等N大潜力名片”这类清单，不能只保留现代农业总项；"
                    "子项名称规范为A产业、B产业，并继承该行的发展方向、项目和证据。"
                    "不要把项目名、产品名或技术名误当成独立产业。证据必须逐字来自切片。"
                    "specific_policy_found 固定为 null，因为规划方向不等于具体扶持政策。"
                    "严格输出一个 JSON 对象。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"目标结构示例：\n{json.dumps(schema, ensure_ascii=False)}\n\n"
                    f"待抽取切片：\n{context}"
                ),
            },
        ]
        payload = {
            "model": self.chat_model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "extra_body": {"enable_thinking": False},
        }
        response = self.session.post(f"{self.base_url}/chat/completions", json=payload, timeout=180)
        if response.status_code >= 400:
            payload.pop("response_format", None)
            payload.pop("extra_body", None)
            response = self.session.post(f"{self.base_url}/chat/completions", json=payload, timeout=180)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        return json.loads(content)

    def select_profile_chunks(self, chunks: list[TextChunk]) -> list[str]:
        candidates = [
            {
                "chunk_id": chunk.chunk_id,
                "kind": chunk.kind,
                "preview": chunk.text[:500],
            }
            for chunk in chunks
        ]
        messages = [
            {
                "role": "system",
                "content": (
                    "你是RAG切片筛选器。请选择直接汇总县域生产性经济产业及其发展目标、"
                    "发展方向、重点项目的切片。优先选择以具体产业为多行记录的总表。"
                    "排除教育、医疗、社会保障、城市更新、一般基础设施、科技服务、"
                    "数字政府、乡村治理和乡镇项目汇总。严格输出JSON。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "返回格式：{\"selected_chunk_ids\":[\"chunk-001\"]}\n"
                    + json.dumps(candidates, ensure_ascii=False)
                ),
            },
        ]
        payload = {
            "model": self.chat_model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "extra_body": {"enable_thinking": False},
        }
        response = self.session.post(f"{self.base_url}/chat/completions", json=payload, timeout=120)
        if response.status_code >= 400:
            payload.pop("response_format", None)
            payload.pop("extra_body", None)
            response = self.session.post(f"{self.base_url}/chat/completions", json=payload, timeout=120)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
        selected = json.loads(content).get("selected_chunk_ids", [])
        valid_ids = {chunk.chunk_id for chunk in chunks}
        return [chunk_id for chunk_id in selected if chunk_id in valid_ids]


def _cosine(left: Iterable[float], right: Iterable[float]) -> float:
    pairs = list(zip(left, right))
    dot = sum(a * b for a, b in pairs)
    left_norm = math.sqrt(sum(a * a for a, _ in pairs))
    right_norm = math.sqrt(sum(b * b for _, b in pairs))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def retrieve_chunks(
    client: DashScopeClient,
    chunks: list[TextChunk],
    queries: list[str] | None = None,
    top_k: int = 12,
) -> list[tuple[TextChunk, float]]:
    queries = queries or DEFAULT_RETRIEVAL_QUERIES
    vectors = client.embeddings([chunk.text for chunk in chunks] + queries)
    chunk_vectors = vectors[: len(chunks)]
    query_vectors = vectors[len(chunks) :]
    ranked = []
    for chunk, vector in zip(chunks, chunk_vectors):
        score = max(_cosine(vector, query_vector) for query_vector in query_vectors)
        if chunk.kind == "table" and re.search(r"专栏\s*\d+", chunk.text):
            score += 0.05
        ranked.append((chunk, score))
    return sorted(ranked, key=lambda item: item[1], reverse=True)[:top_k]


def validate_profile(profile: dict) -> dict:
    industries = profile.get("industries")
    if not isinstance(industries, list):
        raise ValueError("Qwen 输出缺少 industries 数组")
    seen = set()
    cleaned = []
    for row in industries:
        industry = _clean(str(row.get("industry", "")))
        if not industry or industry in seen:
            continue
        seen.add(industry)
        row["industry"] = industry
        row.setdefault("parent_industry", None)
        row["specific_policy_found"] = None
        cleaned.append(row)
    profile["industries"] = cleaned
    return profile


def exclude_non_industry_summaries(chunks: list[TextChunk]) -> list[TextChunk]:
    """Remove public-service and place-building summaries from productive-industry context."""
    return [
        chunk
        for chunk in chunks
        if not any(term in chunk.text.split("\n", 1)[0] for term in NON_INDUSTRY_SUMMARY_TERMS)
    ]


def attach_evidence_from_chunks(profile: dict, chunks: list[TextChunk]) -> dict:
    """Replace weak model citations with an exact source row containing the industry."""
    for row in profile.get("industries", []):
        industry = re.sub(r"产业$", "", row.get("industry", ""))
        parent = re.sub(r"产业$", "", row.get("parent_industry") or "")
        matches = []
        for chunk in chunks:
            for line in chunk.text.splitlines():
                if industry and industry in line:
                    first_cell = line.split(" | ", 1)[0]
                    first_key = re.sub(r"产业$", "", first_cell)
                    score = 10 if first_key == industry else 1
                    if parent and first_key == parent and industry in line:
                        score = 8
                    matches.append((score, chunk.chunk_id, line))
        if matches:
            _, chunk_id, quote = max(matches, key=lambda item: (item[0], len(item[2])))
            row["evidence"] = [{"chunk_id": chunk_id, "quote": quote}]
    return profile


def ensure_table_industries(profile: dict, chunks: list[TextChunk]) -> dict:
    """Repair LLM omissions when a retrieved chunk exposes a regular four-column table."""
    industries = profile.setdefault("industries", [])

    def key(name: str) -> str:
        return re.sub(r"产业$", "", _clean(name))

    top_level_keys = set()
    for chunk in chunks:
        for line in chunk.text.splitlines():
            cells = [_clean(cell) for cell in line.split(" | ")]
            if len(cells) == 4 and cells[0] not in {"产业", "板块"} and len(cells[0]) <= 20:
                top_level_keys.add(key(cells[0]))

    for row in industries:
        if key(row.get("industry", "")) in top_level_keys:
            row["parent_industry"] = None

    existing = {key(row.get("industry", "")) for row in industries}
    for chunk in chunks:
        for line in chunk.text.splitlines():
            cells = [_clean(cell) for cell in line.split(" | ")]
            if len(cells) != 4 or cells[0] in {"产业", "板块"}:
                continue
            raw_industry, goal, directions, projects = cells
            if not raw_industry or len(raw_industry) > 20 or key(raw_industry) in existing:
                continue
            industry = raw_industry if raw_industry.endswith("产业") else f"{raw_industry}产业"
            industries.append(
                {
                    "county": profile.get("county", ""),
                    "industry": industry,
                    "parent_industry": None,
                    "industry_aliases": [raw_industry] if raw_industry != industry else [],
                    "development_goal": goal,
                    "development_directions": [
                        re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩]\s*", "", item).strip("。 ")
                        for item in re.split(r"[；;]", directions)
                        if item.strip("。 ")
                    ],
                    "planned_actions": [],
                    "planned_projects": [
                        item.strip("。 ") for item in re.split(r"[、，,]", projects) if item.strip("。 ")
                    ],
                    "mentioned_in_plan": True,
                    "specific_policy_found": None,
                    "source_document": profile.get("source_document", ""),
                    "source_url": profile.get("source_url", ""),
                    "plan_period": profile.get("plan_period", ""),
                    "evidence": [{"chunk_id": chunk.chunk_id, "quote": line}],
                }
            )
            existing.add(key(raw_industry))
    return profile


PROFILE_FILES = {
    "2021-2025": "yongchun_industry_profile_2021_2025.json",
    "2026-2030": "yongchun_industry_profile.json",
}


def load_industry_profile(project_root: Path, plan_period: str = "2026-2030") -> list[dict]:
    """Load one plan-period profile while preserving the fifteenth-plan default."""
    try:
        filename = PROFILE_FILES[plan_period]
    except KeyError as error:
        raise ValueError(f"不支持的规划期：{plan_period}") from error
    path = project_root / "data" / "processed" / filename
    return json.loads(path.read_text(encoding="utf-8"))["industries"]


def compare_plan_mentions(
    query: str,
    fourteenth_profile: list[dict],
    fifteenth_profile: list[dict],
) -> dict:
    """Retrieve the same user query from both profiles for an on-demand comparison."""
    fourteenth_matches = search_industry_profile(query, fourteenth_profile, limit=1)
    fifteenth_matches = search_industry_profile(query, fifteenth_profile, limit=1)
    fourteenth_match = fourteenth_matches[0] if fourteenth_matches else None
    fifteenth_match = fifteenth_matches[0] if fifteenth_matches else None

    if fourteenth_match and fifteenth_match:
        comparison = "十四五、十五五均提及"
        policy_level = 2
    elif fifteenth_match:
        comparison = "十五五新增"
        policy_level = 3
    elif fourteenth_match:
        comparison = "十四五提及，十五五未提及"
        policy_level = 1
    else:
        comparison = "未提及"
        policy_level = 0

    return {
        "fourteenth": fourteenth_match,
        "fifteenth": fifteenth_match,
        "comparison": comparison,
        "policy_level": policy_level,
        "policy_score": round(policy_level / 3 * 100, 1),
    }


def _search_normalize(value: str) -> str:
    value = re.sub(r"[\s，。、“”‘’（）()·/]+", "", str(value)).lower()
    return re.sub(r"(?:产业|行业)$", "", value)


def search_industry_profile(query: str, rows: list[dict], limit: int = 3) -> list[dict]:
    """Lightweight local retrieval for the demo."""
    needle = _search_normalize(query)
    if not needle:
        return []
    ranked = []
    for row in rows:
        names = [row.get("industry", ""), *row.get("industry_aliases", [])]
        score = 0.0
        for name in names:
            candidate = _search_normalize(name)
            if not candidate:
                continue
            if needle == candidate:
                score = max(score, 1.0)
            elif candidate in needle:
                score = max(score, 0.98)
            elif needle in candidate:
                score = max(score, 0.93)
            else:
                overlap = len(set(needle) & set(candidate))
                score = max(score, 0.8 * 2 * overlap / (len(set(needle)) + len(set(candidate))))

        descriptive_text = " ".join(
            [
                str(row.get("development_goal", "")),
                *map(str, row.get("development_directions", [])),
                *map(str, row.get("planned_projects", [])),
            ]
        )
        if needle in _search_normalize(descriptive_text):
            score = max(score, 0.75)
        if score >= 0.65:
            matched = dict(row)
            matched["match_score"] = round(score, 3)
            ranked.append(matched)
    return sorted(ranked, key=lambda row: row["match_score"], reverse=True)[:limit]
