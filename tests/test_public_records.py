from scripts.fetch_public_records import extract_policy_records, parse_land_transfer


def test_parse_land_transfer_table():
    html = """
    <table>
      <tr><td colspan="3">汇总表</td></tr>
      <tr><td>流入方名称</td><td>流转总面积（亩）</td><td>流转单价（元/亩/年）</td></tr>
      <tr><td>甲</td><td>20</td><td>100</td></tr>
      <tr><td>合计</td><td>20</td><td>100</td></tr>
    </table>
    """
    result = parse_land_transfer(html)
    assert len(result) == 1
    assert result.iloc[0]["area_mu"] == 20
    assert result.iloc[0]["price_yuan_per_mu_year"] == 100


def test_policy_extraction_fails_closed_when_page_changes():
    policy_2025 = "30亩 100亩 100元 200元 撂荒 500元 300元"
    policies = extract_policy_records(policy_2025, "94.01元")
    assert len(policies) == 9
    assert any(policy["subsidy_yuan_per_mu"] == 94.01 for policy in policies)
