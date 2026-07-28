"""验证 UI Fixture 生命周期和 BrowserContext 状态隔离。"""

from __future__ import annotations

import json


ISOLATION_URL = "https://context-isolation.test/state"
ISOLATION_ROUTE = "**/state"


def _serve_state_page(route, body: str):
    route.fulfill(
        status=200,
        content_type="text/html",
        body=f"<html><body>{body}</body></html>",
    )


def test_browser_context_isolation_contract(browser, context, page, request):
    """认证、偏好、缓存和 Mock 均不得进入另一个 Context。"""
    fixture_defs = request._fixture_defs
    assert fixture_defs["browser"].scope == "session"
    assert fixture_defs["context"].scope == "function"
    assert fixture_defs["page"].scope == "function"

    context.route(
        ISOLATION_ROUTE,
        lambda route: _serve_state_page(route, "mock-from-first-context"),
    )
    page.goto(ISOLATION_URL, wait_until="domcontentloaded")
    assert page.locator("body").inner_text() == "mock-from-first-context"

    context.add_cookies(
        [
            {
                "name": "auth_token",
                "value": "logged-in-from-first-context",
                "domain": "context-isolation.test",
                "path": "/",
            }
        ]
    )
    page.evaluate(
        """
        async () => {
            localStorage.setItem('language', 'zh-CN');
            localStorage.setItem('currency', 'CNY');
            localStorage.setItem('auth_state', 'logged-in');
            sessionStorage.setItem('search_state', 'first-context-only');
            const cache = await caches.open('jetbay-test-cache');
            await cache.put('/cached-profile', new Response('first-context-profile'));
        }
        """
    )

    second_context = browser.new_context(viewport={"width": 1920, "height": 1080})
    try:
        second_context.route(
            ISOLATION_ROUTE,
            lambda route: _serve_state_page(route, "fresh-second-context"),
        )
        second_page = second_context.new_page()
        second_page.goto(ISOLATION_URL, wait_until="domcontentloaded")

        # 返回新内容，证明第一个 Context 的 Mock 没有串入第二个 Context。
        assert second_page.locator("body").inner_text() == "fresh-second-context"
        cookies = {
            cookie["name"]: cookie["value"]
            for cookie in second_context.cookies(ISOLATION_URL)
        }
        assert "auth_token" not in cookies

        state = second_page.evaluate(
            """
            async () => ({
                localStorage: {...localStorage},
                sessionStorage: {...sessionStorage},
                cacheKeys: await caches.keys(),
            })
            """
        )
        assert state == {
            "localStorage": {},
            "sessionStorage": {},
            "cacheKeys": [],
        }, json.dumps(state, ensure_ascii=False, indent=2)
    finally:
        second_context.close()
