from __future__ import annotations

import argparse
import json
import re
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


LAND_TRANSFER_URL = (
    "https://www.fjyc.gov.cn/ztzl/jczwgk/xzlybzxx/xyzly/"
    "202412/t20241224_3121358.htm"
)
TAOCHENG_TRANSFER_URL = (
    "https://www.fjyc.gov.cn/ztzl/jczwgk/xzlybzxx/tcz/"
    "202312/t20231229_2987527.htm"
)
JIEFU_TRANSFER_URL = (
    "https://www.fjyc.gov.cn/ztzl/jczwgk/xzlybzxx/jfxly/"
    "202512/t20251223_3245095.htm"
)
POLICY_2025_URL = (
    "https://www.fjyc.gov.cn/zwgk/jdhy/bdzcjd/"
    "202504/t20250427_3164162.htm"
)
POLICY_2026_URL = (
    "https://www.fjyc.gov.cn/zwgk/zfxxgkzl/xzbm/nyncj/ml/"
    "202606/t20260626_3304156.htm"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="抓取永春县土地流转和种植补贴公开记录。")
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--archive-dir", type=Path, default=Path("data/raw/public_pages"))
    return parser.parse_args()


def make_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=4,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 Chrome/131 Safari/537.36"
            )
        }
    )
    return session


def fetch_html(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=45)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def clean_text(html: str) -> str:
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)


def parse_land_transfer(html: str) -> pd.DataFrame:
    tables = pd.read_html(StringIO(html))
    if not tables:
        raise ValueError("土地流转页面中没有表格。")
    table = max(tables, key=len).copy()
    header_row = next(
        (index for index, row in table.iterrows() if row.astype(str).str.contains("流转总面积").any()),
        None,
    )
    if header_row is None:
        raise ValueError("无法识别土地流转表头，页面结构可能已改变。")
    table.columns = [str(value).strip() for value in table.iloc[header_row]]
    table = table.iloc[header_row + 1 :].copy()
    table = table[~table.iloc[:, 0].astype(str).str.contains("合计", na=False)]
    table = table.dropna(how="all")

    rename = {
        "流入方名称": "transferee",
        "流入方类型": "transferee_type",
        "流出方名称": "transferor",
        "流转用途": "land_use",
        "流转总面积（亩）": "area_mu",
        "其中粮食面积（亩）": "grain_area_mu",
        "流转起始时间": "start_date",
        "流转结束时间": "end_date",
        "流转方式": "transfer_method",
        "流转单价（元/亩/年）": "price_yuan_per_mu_year",
    }
    table = table.rename(columns=rename)
    required = ["area_mu", "price_yuan_per_mu_year"]
    if any(column not in table for column in required):
        raise ValueError("土地流转表缺少面积或单价字段，页面结构可能已改变。")
    for column in required + ["grain_area_mu"]:
        if column in table:
            table[column] = pd.to_numeric(table[column], errors="coerce")
    table.insert(0, "town", "下洋镇")
    table.insert(
        1,
        "village",
        table.get("transferor", pd.Series(index=table.index, dtype=object))
        .astype(str)
        .str.extract(r"镇([^，,、]+?村)村民委员会", expand=False)
        .fillna("unknown"),
    )
    table["published_date"] = "2024-12-24"
    table["source_url"] = LAND_TRANSFER_URL
    table["scope_note"] = "仅为下洋镇2024年公开交易样本，不代表永春县统一租金"
    table["transcription_method"] = "HTML结构化表格"
    return table.reset_index(drop=True)


def transcribed_land_transfer_records() -> pd.DataFrame:
    """政府网页只以内嵌图片发布表格，以下为图片逐行转录并保留来源。"""
    rows = [
        ("桃城镇", "花石社区", 41.0, 1500.0, "水稻", "2023-12-29", TAOCHENG_TRANSFER_URL),
        ("桃城镇", "仓山村", 152.7, 240.0, "果树种植", "2023-12-29", TAOCHENG_TRANSFER_URL),
        ("桃城镇", "仓山村", 654.62, 200.0, "中药材百步", "2023-12-29", TAOCHENG_TRANSFER_URL),
        ("桃城镇", "洋上村", 45.0, 300.0, "水稻", "2023-12-29", TAOCHENG_TRANSFER_URL),
        ("介福乡", "福东村", 113.0, 600.0, "农作物种植", "2025-12-23", JIEFU_TRANSFER_URL),
        ("介福乡", "福东村", 107.0, 600.0, "农作物种植", "2025-12-23", JIEFU_TRANSFER_URL),
        ("介福乡", "福东村", 92.0, 600.0, "农作物种植", "2025-12-23", JIEFU_TRANSFER_URL),
        ("介福乡", "福东村", 87.0, 600.0, "农作物种植", "2025-12-23", JIEFU_TRANSFER_URL),
        ("介福乡", "紫美村", 65.0, 600.0, "农作物种植", "2025-12-23", JIEFU_TRANSFER_URL),
    ]
    return pd.DataFrame(
        [
            {
                "town": town,
                "village": village,
                "land_use": use,
                "area_mu": area,
                "price_yuan_per_mu_year": price,
                "published_date": date,
                "source_url": url,
                "scope_note": "政府网页内嵌表格图片人工转录；使用前应回看原图复核",
                "transcription_method": "内嵌图片人工转录",
            }
            for town, village, area, price, use, date, url in rows
        ]
    )


def extract_policy_records(policy_2025_text: str, policy_2026_text: str) -> list[dict]:
    checks = {
        "2025粮油规模种植补助": ["30亩", "100亩", "100元", "200元"],
        "2025撂荒耕地复垦种粮补助": ["撂荒", "500元", "300元"],
        "2026耕地地力保护补贴": ["94.01元"],
    }
    source_text = {
        "2025粮油规模种植补助": policy_2025_text,
        "2025撂荒耕地复垦种粮补助": policy_2025_text,
        "2026耕地地力保护补贴": policy_2026_text,
    }
    for name, tokens in checks.items():
        missing = [token for token in tokens if token not in source_text[name]]
        if missing:
            raise ValueError(f"{name}页面缺少预期字段：{', '.join(missing)}")

    return [
        {
            "policy_id": "YC-2025-GRAIN-30-100",
            "name": "粮油规模种植补助",
            "crop_scope": ["水稻", "甘薯", "玉米"],
            "minimum_area_mu": 30,
            "maximum_area_mu": 100,
            "subsidy_yuan_per_mu": 100,
            "frequency": "每季",
            "condition": "相对连片种植30亩以上、100亩以下",
            "source_url": POLICY_2025_URL,
            "published_year": 2025,
        },
        {
            "policy_id": "YC-2025-GRAIN-100",
            "name": "粮油规模种植补助",
            "crop_scope": ["水稻", "甘薯", "玉米"],
            "minimum_area_mu": 100,
            "maximum_area_mu": None,
            "subsidy_yuan_per_mu": 200,
            "frequency": "每季",
            "condition": "相对连片种植100亩以上",
            "source_url": POLICY_2025_URL,
            "published_year": 2025,
        },
        {
            "policy_id": "YC-2025-NEW-TRANSFER-100",
            "name": "新增流转耕地种粮补助",
            "crop_scope": ["粮食作物"],
            "minimum_area_mu": 100,
            "maximum_area_mu": None,
            "subsidy_yuan_per_mu": 100,
            "frequency": "一次性",
            "condition": "2025年1月1日以后新增流转耕地100亩以上用于种粮",
            "source_url": POLICY_2025_URL,
            "published_year": 2025,
        },
        {
            "policy_id": "YC-2025-UPLAND-20",
            "name": "旱粮油料规模种植补助",
            "crop_scope": ["大豆", "马铃薯", "旱稻", "花生"],
            "minimum_area_mu": 20,
            "maximum_area_mu": None,
            "subsidy_yuan_per_mu": 200,
            "frequency": "每季",
            "condition": "相对连片种植20亩以上",
            "source_url": POLICY_2025_URL,
            "published_year": 2025,
        },
        {
            "policy_id": "YC-2025-ABANDONED-RICE-10",
            "name": "撂荒耕地复垦种粮补助",
            "crop_scope": ["水稻"],
            "minimum_area_mu": 10,
            "maximum_area_mu": None,
            "subsidy_yuan_per_mu": 500,
            "frequency": "按政策申报",
            "condition": "复垦相对集中连片撂荒耕地10亩以上种植水稻",
            "source_url": POLICY_2025_URL,
            "published_year": 2025,
        },
        {
            "policy_id": "YC-2025-ABANDONED-DRY-10",
            "name": "撂荒耕地复垦种粮补助",
            "crop_scope": ["甘薯", "玉米", "大豆", "马铃薯", "旱稻", "花生"],
            "minimum_area_mu": 10,
            "maximum_area_mu": None,
            "subsidy_yuan_per_mu": 300,
            "frequency": "按政策申报",
            "condition": "复垦相对集中连片撂荒耕地10亩以上种植旱粮",
            "source_url": POLICY_2025_URL,
            "published_year": 2025,
        },
        {
            "policy_id": "YC-2025-ABANDONED-50-EXTRA",
            "name": "撂荒耕地连片复垦叠加补助",
            "crop_scope": ["粮食作物"],
            "minimum_area_mu": 50,
            "maximum_area_mu": None,
            "subsidy_yuan_per_mu": 100,
            "frequency": "叠加补助",
            "condition": "连片复垦撂荒山垅田50亩以上；与基础补助如何叠加以审核为准",
            "source_url": POLICY_2025_URL,
            "published_year": 2025,
        },
        {
            "policy_id": "YC-2026-FERTILITY",
            "name": "耕地地力保护补贴",
            "crop_scope": ["符合补贴条件的耕地"],
            "minimum_area_mu": 0,
            "maximum_area_mu": None,
            "subsidy_yuan_per_mu": 94.01,
            "frequency": "年度",
            "condition": "原则上补给耕地承包权人；流转双方有书面约定的从其约定，并以审核为准",
            "source_url": POLICY_2026_URL,
            "published_year": 2026,
        },
        {
            "policy_id": "YC-2026-SCALE-GRAIN-30",
            "name": "规模种粮主体叠加补贴",
            "crop_scope": ["粮食作物"],
            "minimum_area_mu": 30,
            "maximum_area_mu": None,
            "subsidy_yuan_per_mu": 100,
            "frequency": "当年补上年",
            "condition": "30亩以上规模种粮主体；与其他政策的重复享受规则须复核",
            "source_url": POLICY_2026_URL,
            "published_year": 2026,
        },
    ]


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.archive_dir.mkdir(parents=True, exist_ok=True)
    session = make_session()

    pages = {
        "land_transfer_2024_xiayang.html": fetch_html(session, LAND_TRANSFER_URL),
        "land_transfer_2023_taocheng.html": fetch_html(session, TAOCHENG_TRANSFER_URL),
        "land_transfer_2025_jiefu.html": fetch_html(session, JIEFU_TRANSFER_URL),
        "planting_policy_2025.html": fetch_html(session, POLICY_2025_URL),
        "farmland_subsidy_2026.html": fetch_html(session, POLICY_2026_URL),
    }
    for filename, html in pages.items():
        (args.archive_dir / filename).write_text(html, encoding="utf-8")

    for filename in ("land_transfer_2023_taocheng.html", "land_transfer_2025_jiefu.html"):
        if "data:image" not in pages[filename]:
            raise ValueError(f"{filename}没有找到预期内嵌表格图片，需重新人工复核。")
    transfers = pd.concat(
        [parse_land_transfer(pages["land_transfer_2024_xiayang.html"]), transcribed_land_transfer_records()],
        ignore_index=True,
    )
    transfers.to_csv(args.output_dir / "land_transfer_samples.csv", index=False)

    policies = extract_policy_records(
        clean_text(pages["planting_policy_2025.html"]),
        clean_text(pages["farmland_subsidy_2026.html"]),
    )
    (args.output_dir / "planting_subsidies.json").write_text(
        json.dumps(policies, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    sources = pd.DataFrame(
        [
            {
                "dataset": "下洋镇农村土地承包经营权流转样本",
                "type": "HTML表格/爬取",
                "spatial_scope": "下洋镇",
                "time": "2024",
                "output": "land_transfer_samples.csv",
                "source_url": LAND_TRANSFER_URL,
                "mvp_use": "镇级土地成本；其他镇缺失时使用全部样本中位数回填",
            },
            {
                "dataset": "桃城镇与介福乡农村土地流转样本",
                "type": "政府网页内嵌图片/人工转录",
                "spatial_scope": "桃城镇、介福乡",
                "time": "2023、2025",
                "output": "land_transfer_samples.csv",
                "source_url": f"{TAOCHENG_TRANSFER_URL} | {JIEFU_TRANSFER_URL}",
                "mvp_use": "镇级土地成本；保留人工转录标记",
            },
            {
                "dataset": "永春县粮油生产扶持措施",
                "type": "政府网页/规则抽取",
                "spatial_scope": "永春县",
                "time": "2025",
                "output": "planting_subsidies.json",
                "source_url": POLICY_2025_URL,
                "mvp_use": "按作物和面积匹配政策，待接入评分",
            },
            {
                "dataset": "永春县耕地地力保护补贴",
                "type": "政府网页/规则抽取",
                "spatial_scope": "永春县",
                "time": "2026",
                "output": "planting_subsidies.json",
                "source_url": POLICY_2026_URL,
                "mvp_use": "县级共同政策，正式申报资格需复核",
            },
        ]
    )
    sources.to_csv(args.output_dir / "public_data_sources.csv", index=False)
    print(f"已写入 {len(transfers)} 条土地流转样本和 {len(policies)} 条补贴规则。")


if __name__ == "__main__":
    main()
