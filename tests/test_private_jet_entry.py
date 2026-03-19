from pages.private_jet_page import PrivateJetPage


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
