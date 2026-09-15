from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from gover_mvp.policy_profile import (
    DashScopeClient,
    attach_evidence_from_chunks,
    exclude_non_industry_summaries,
    extract_article,
    extract_docx,
    fetch_html,
    ensure_table_industries,
    load_env_file,
    retrieve_chunks,
    validate_profile,
)


DEFAULT_URL = "https://www.fjyc.gov.cn/zwgk/zfxxgkzl/ml/ghjh/202608/t20260803_3315323.htm"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从五年规划文字版生成县×产业画像。")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--input-docx", type=Path)
    parser.add_argument("--county", default="永春县")
    parser.add_argument("--plan-period", default="2026-2030")
    parser.add_argument("--top-k", type=int, default=12)
    parser.add_argument("--output", type=Path, default=Path("data/processed/yongchun_industry_profile.json"))
    parser.add_argument("--retrieval-output", type=Path, default=Path("data/interim/policy_profile_retrieval.json"))
    parser.add_argument("--reuse-retrieval", action="store_true")
    parser.add_argument("--reuse-selection", action="store_true")
    parser.add_argument("--postprocess-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.postprocess_only:
        from gover_mvp.policy_profile import TextChunk

        profile = json.loads(args.output.read_text(encoding="utf-8"))
        cached = json.loads(args.retrieval_output.read_text(encoding="utf-8"))
        selected = set(profile.get("selected_chunk_ids", []))
        chunks = [
            TextChunk(item["chunk_id"], item["text"], item["kind"])
            for item in cached["chunks"]
            if item["chunk_id"] in selected
        ]
        profile = attach_evidence_from_chunks(profile, chunks)
        profile = ensure_table_industries(profile, chunks)
        args.output.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已更新 {len(profile['industries'])} 条画像的原文证据：{args.output}")
        return

    load_env_file(Path(".env"))
    required = ["DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL", "DASHSCOPE_MODEL"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError(f"缺少环境配置：{', '.join(missing)}")

    if args.reuse_retrieval:
        cached = json.loads(args.retrieval_output.read_text(encoding="utf-8"))
        title = cached["source_document"]
        from gover_mvp.policy_profile import TextChunk

        retrieved = [
            (TextChunk(item["chunk_id"], item["text"], item["kind"]), float(item["score"]))
            for item in cached["chunks"]
        ]
    else:
        if args.input_docx:
            title, chunks = extract_docx(args.input_docx)
        else:
            html = fetch_html(args.url)
            title, chunks = extract_article(html)
    client = DashScopeClient(
        api_key=os.environ["DASHSCOPE_API_KEY"],
        base_url=os.environ["DASHSCOPE_BASE_URL"],
        chat_model=os.environ["DASHSCOPE_MODEL"],
        embedding_model=os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v4"),
    )
    if not args.reuse_retrieval:
        print(f"正文已切分为 {len(chunks)} 块，开始向量召回……", flush=True)
        retrieved = retrieve_chunks(client, chunks, top_k=args.top_k)
        retrieval_payload = {
        "source_url": str(args.input_docx or args.url),
            "source_document": title,
            "chunks": [
                {"chunk_id": chunk.chunk_id, "kind": chunk.kind, "score": round(score, 6), "text": chunk.text}
                for chunk, score in retrieved
            ],
        }
        args.retrieval_output.parent.mkdir(parents=True, exist_ok=True)
        args.retrieval_output.write_text(
            json.dumps(retrieval_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    retrieved_chunks = [chunk for chunk, _ in retrieved]
    selected_ids = []
    if args.reuse_selection and args.output.exists():
        selected_ids = json.loads(args.output.read_text(encoding="utf-8")).get("selected_chunk_ids", [])
    if not selected_ids:
        selected_ids = client.select_profile_chunks(retrieved_chunks)
    selected_chunks = exclude_non_industry_summaries(
        [chunk for chunk in retrieved_chunks if chunk.chunk_id in selected_ids]
    )
    if not selected_chunks:
        selected_chunks = retrieved_chunks[:5]
    context = "\n\n".join(f"[{chunk.chunk_id}]\n{chunk.text}" for chunk in selected_chunks)
    print(
        f"已召回 {len(retrieved)} 块，Qwen 精选 {len(selected_chunks)} 块："
        f"{', '.join(chunk.chunk_id for chunk in selected_chunks)}",
        flush=True,
    )
    print("开始用 Qwen 生成画像……", flush=True)
    source_reference = str(args.input_docx or args.url)
    profile = validate_profile(
        client.extract_profile(context, args.county, title, source_reference, args.plan_period)
    )
    profile = attach_evidence_from_chunks(profile, selected_chunks)
    profile["county"] = args.county
    profile["source_document"] = title
    profile["source_url"] = source_reference
    profile["plan_period"] = args.plan_period
    profile["retrieved_chunk_count"] = len(retrieved)
    profile["selected_chunk_ids"] = [chunk.chunk_id for chunk in selected_chunks]
    profile = ensure_table_industries(profile, selected_chunks)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成 {len(profile['industries'])} 条县×产业画像：{args.output}")


if __name__ == "__main__":
    main()
