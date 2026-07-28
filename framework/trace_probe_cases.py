"""仅供 Trace 生命周期集成测试显式调用，不参与常规 pytest 收集。"""


def test_trace_probe_success(page):
    page.set_content("<button id='ok'>success probe</button>")
    page.locator("#ok").click()
    assert page.locator("#ok").inner_text() == "success probe"


def test_trace_probe_failure(page):
    page.set_content("<button id='fail'>failure probe</button>")
    page.locator("#fail").click()
    assert page.locator("#fail").inner_text() == "unexpected text"
