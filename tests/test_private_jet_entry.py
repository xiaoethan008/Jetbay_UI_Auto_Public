from pages.private_jet_page import PrivateJetPage
from runtime_environments import get_current_environment


def _get_clip_state(locator):
    """计算元素被 overflow-hidden / clip 父容器裁切后的实际可见比例。"""
    return locator.evaluate(
        """
        el => {
          const rect = el.getBoundingClientRect();
          let left = rect.left;
          let top = rect.top;
          let right = rect.right;
          let bottom = rect.bottom;
          const clippedBy = [];

          for (let node = el.parentElement; node; node = node.parentElement) {
            const style = getComputedStyle(node);
            const overflow = `${style.overflow} ${style.overflowX} ${style.overflowY}`;
            if (!/(hidden|clip)/.test(overflow)) {
              continue;
            }

            const nodeRect = node.getBoundingClientRect();
            const before = { left, top, right, bottom };
            left = Math.max(left, nodeRect.left);
            top = Math.max(top, nodeRect.top);
            right = Math.min(right, nodeRect.right);
            bottom = Math.min(bottom, nodeRect.bottom);

            if (
              left !== before.left ||
              top !== before.top ||
              right !== before.right ||
              bottom !== before.bottom
            ) {
              clippedBy.push({
                tag: node.tagName,
                className: node.className,
                overflow,
                rect: {
                  x: nodeRect.x,
                  y: nodeRect.y,
                  width: nodeRect.width,
                  height: nodeRect.height,
                  bottom: nodeRect.bottom,
                },
              });
            }
          }

          const visibleWidth = Math.max(0, right - left);
          const visibleHeight = Math.max(0, bottom - top);
          const area = Math.max(1, rect.width * rect.height);

          return {
            text: el.innerText,
            rect: {
              x: rect.x,
              y: rect.y,
              width: rect.width,
              height: rect.height,
              bottom: rect.bottom,
            },
            visible: {
              width: visibleWidth,
              height: visibleHeight,
              ratio: (visibleWidth * visibleHeight) / area,
            },
            clippedBy,
          };
        }
        """
    )


def test_open_private_jet_from_home(home_page, page):
    """从首页进入 Private Jet 页面，并检查图片和链接可用性。"""
    home_page.open_private_jet_from_home()

    private_jet = PrivateJetPage(page)
    private_jet.wait_for_page()

    broken_images = private_jet.get_broken_page_images()
    inaccessible_links = private_jet.get_inaccessible_links()

    if broken_images:
        print("\n[private-jet] broken images found:")
        for image in broken_images:
            print(
                f"index={image.get('index')}, alt={image.get('alt')}, src={image.get('src')}"
            )

    assert private_jet.has_expected_content()
    assert broken_images == [], f"Broken Private Jet images: {broken_images}"
    assert inaccessible_links == [], f"Inaccessible Private Jet links: {inaccessible_links}"


def test_private_jet_multi_city_three_legs_keeps_search_cta_visible(page):
    """Multi-City 添加第三段航程后，底部搜索按钮不能被 Hero 容器裁切。"""
    page.set_viewport_size({"width": 1900, "height": 817})
    base_url = get_current_environment()["base_url"].rstrip("/")
    page.goto(f"{base_url}/private-jet-charter", wait_until="networkidle")

    # 复现历史问题：多程表单增加到 3 段后，表单高度会超过 Hero 区域。
    page.get_by_text("Multi-City", exact=True).click()
    page.get_by_text("Add another flight", exact=True).click()

    search_button = page.locator("button:has-text('Search Available Aircraft')").last
    search_button.wait_for(state="attached")
    clip_state = _get_clip_state(search_button)

    # 只判断 overflow 裁切后的实际可见比例，避免“DOM 存在但用户看不到”的假通过。
    assert clip_state["visible"]["ratio"] >= 0.95, (
        "Multi-City Search Available Aircraft button is clipped by an overflow-hidden "
        f"ancestor: {clip_state}"
    )
