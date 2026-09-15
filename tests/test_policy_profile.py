from gover_mvp.policy_profile import (
    TextChunk,
    attach_evidence_from_chunks,
    compare_plan_mentions,
    exclude_non_industry_summaries,
    extract_article,
    extract_docx,
    ensure_table_industries,
    search_industry_profile,
    validate_profile,
)


def test_extract_article_keeps_policy_table_as_one_chunk():
    html = """
    <div class="article_title">某县十五五规划</div>
    <div class="article_content">
      <p>第二章 产业发展</p>
      <table>
        <tr><td colspan="2">专栏3：特色产业发展重大工程</td></tr>
        <tr><th>产业</th><th>发展目标</th></tr>
        <tr><td>竹产业</td><td>建设竹基新材料产业</td></tr>
      </table>
      <p>第三章 民生事业</p>
    </div>
    """
    title, chunks = extract_article(html)
    assert title == "某县十五五规划"
    table_chunks = [chunk for chunk in chunks if chunk.kind == "table"]
    assert len(table_chunks) == 1
    assert "竹产业 | 建设竹基新材料产业" in table_chunks[0].text


def test_validate_profile_deduplicates_industries_and_keeps_unknown_policy_state():
    result = validate_profile(
        {
            "industries": [
                {"industry": "竹产业", "specific_policy_found": True},
                {"industry": " 竹产业 ", "specific_policy_found": False},
                {"industry": "茶产业"},
            ]
        }
    )
    assert [row["industry"] for row in result["industries"]] == ["竹产业", "茶产业"]
    assert all(row["specific_policy_found"] is None for row in result["industries"])


def test_exclude_non_industry_summaries_removes_infrastructure_table():
    chunks = [
        TextChunk("chunk-1", "专栏：产业基础设施重大工程\n产业园区", "table"),
        TextChunk("chunk-2", "专栏：特色产业发展重大工程\n香产业", "table"),
    ]
    assert [chunk.chunk_id for chunk in exclude_non_industry_summaries(chunks)] == ["chunk-2"]


def test_attach_evidence_prefers_row_with_parent_and_child_industry():
    profile = {"industries": [{"industry": "竹产业", "parent_industry": "现代农业产业"}]}
    chunks = [
        TextChunk("chunk-1", "新材料 | 高性能竹纤维", "table"),
        TextChunk("chunk-2", "现代农业 | 做强芦柑、茶、花、竹、蜂蜜五大潜力名片", "table"),
    ]
    result = attach_evidence_from_chunks(profile, chunks)
    assert result["industries"][0]["evidence"][0]["chunk_id"] == "chunk-2"


def test_ensure_table_industries_repairs_a_missing_row():
    profile = {"county": "永春县", "industries": [{"industry": "现代农业产业"}]}
    chunks = [
        TextChunk(
            "chunk-1",
            "产业 | 发展目标 | 发展方向和重点 | 重点项目\n"
            "现代农业 | 做强农业 | ①特色农业；②智慧农业。 | 茶产业园项目。\n"
            "文旅康养 | 建设目的地 | ①文旅融合。 | 文旅项目。",
            "table",
        )
    ]
    result = ensure_table_industries(profile, chunks)
    assert [row["industry"] for row in result["industries"]] == ["现代农业产业", "文旅康养产业"]


def test_ensure_table_industries_clears_invented_parent_for_top_level_row():
    profile = {"industries": [{"industry": "新材料产业", "parent_industry": "现代农业产业"}]}
    chunks = [
        TextChunk(
            "chunk-1",
            "产业 | 发展目标 | 发展方向和重点 | 重点项目\n"
            "新材料 | 建设产业基地 | 新型材料 | 新材料项目",
            "table",
        )
    ]
    result = ensure_table_industries(profile, chunks)
    assert result["industries"][0]["parent_industry"] is None


def test_search_industry_profile_matches_colloquial_bamboo_query():
    rows = [
        {"industry": "竹产业", "industry_aliases": [], "development_goal": "发展竹产业"},
        {"industry": "新材料产业", "industry_aliases": [], "development_goal": "发展竹纤维材料"},
    ]
    matches = search_industry_profile("竹子", rows)
    assert matches[0]["industry"] == "竹产业"


def test_compare_plan_mentions_retrieves_each_period_at_input_time():
    fourteenth = [{"industry": "轻纺鞋服产业", "industry_aliases": ["纺织"]}]
    fifteenth = [{"industry": "轻工纺织产业", "industry_aliases": ["纺织"]}]

    result = compare_plan_mentions("纺织", fourteenth, fifteenth)

    assert result["fourteenth"]["industry"] == "轻纺鞋服产业"
    assert result["fifteenth"]["industry"] == "轻工纺织产业"
    assert result["comparison"] == "十四五、十五五均提及"
    assert result["policy_level"] == 2
    assert result["policy_score"] == 66.7


def test_compare_plan_mentions_marks_new_fifteenth_plan_mention():
    result = compare_plan_mentions(
        "低空经济",
        [{"industry": "机械制造产业", "industry_aliases": []}],
        [{"industry": "低空经济产业", "industry_aliases": []}],
    )

    assert result["fourteenth"] is None
    assert result["fifteenth"]["industry"] == "低空经济产业"
    assert result["comparison"] == "十五五新增"
    assert result["policy_level"] == 3
    assert result["policy_score"] == 100.0


def test_compare_plan_mentions_scores_fourteenth_only_and_neither():
    fourteenth_only = compare_plan_mentions(
        "机械制造",
        [{"industry": "机械制造产业", "industry_aliases": []}],
        [],
    )
    neither = compare_plan_mentions("航天", [], [])

    assert fourteenth_only["comparison"] == "十四五提及，十五五未提及"
    assert fourteenth_only["policy_level"] == 1
    assert fourteenth_only["policy_score"] == 33.3
    assert neither["comparison"] == "未提及"
    assert neither["policy_level"] == 0
    assert neither["policy_score"] == 0.0
