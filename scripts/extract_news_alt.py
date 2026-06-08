import argparse
import json
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright


DECORATIVE_ALTS = {
    "",
    "new",
    "go-detail",
    "share",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract image alt text for a target article from the Jetbay news list page and detail page."
    )
    parser.add_argument(
        "--list-url",
        default="https://dev.jet-bay.com/zh-cn/news",
        help="News list page URL.",
    )
    parser.add_argument(
        "--title",
        required=True,
        help="Target news title shown on the list page.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode.",
    )
    return parser.parse_args()


def is_meaningful_alt(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip().lower()
    return normalized not in DECORATIVE_ALTS


def main():
    args = parse_args()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=args.headless)
        page = browser.new_page(viewport={"width": 1600, "height": 1200})
        page.set_default_navigation_timeout(90000)
        page.set_default_timeout(30000)

        page.goto(args.list_url, wait_until="networkidle")
        page.wait_for_timeout(2500)

        list_data = page.evaluate(
            """
            ({ title }) => {
              const normalize = (value) => (value || "").replace(/\\s+/g, " ").trim();
              const textMatch = Array.from(document.querySelectorAll("main *")).find(
                (el) => normalize(el.textContent).includes(title)
              );
              if (!textMatch) {
                return { found: false };
              }

              let container = textMatch;
              for (let i = 0; i < 6 && container; i += 1) {
                const imgCount = container.querySelectorAll("img").length;
                const text = normalize(container.textContent);
                if (imgCount > 0 && text.includes(title)) {
                  break;
                }
                container = container.parentElement;
              }

              const listImages = Array.from(container?.querySelectorAll("img") || [])
                .map((img, index) => ({
                  index,
                  alt: img.getAttribute("alt"),
                  currentSrc: img.currentSrc || img.getAttribute("src") || "",
                }));

              const detailButton = Array.from(document.querySelectorAll("main button"))
                .find((button) => normalize(button.textContent).includes("阅读更多"));

              return {
                found: true,
                listImages,
                hasReadMoreButton: !!detailButton,
                containerText: normalize(container?.textContent).slice(0, 300),
              };
            }
            """,
            {"title": args.title},
        )

        if not list_data.get("found"):
            browser.close()
            raise SystemExit(f"Target title not found on list page: {args.title}")

        page.locator("main button").filter(has_text="阅读更多").first.click(force=True)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3000)

        for _ in range(6):
            page.mouse.wheel(0, 1600)
            page.wait_for_timeout(400)

        detail_images = page.evaluate(
            """
            () => {
              return Array.from(document.querySelectorAll("main img"))
                .map((img, index) => {
                  const rect = img.getBoundingClientRect();
                  return {
                    index,
                    alt: img.getAttribute("alt"),
                    currentSrc: img.currentSrc || img.getAttribute("src") || "",
                    visible: !!(rect.width && rect.height),
                    parentText: ((img.closest("figure, section, article, div, main")?.textContent) || "")
                      .replace(/\\s+/g, " ")
                      .trim()
                      .slice(0, 220),
                  };
                })
                .filter((item) => item.visible);
            }
            """
        )

        result = {
            "list_url": args.list_url,
            "title": args.title,
            "list_page": {
                "images": list_data["listImages"],
                "seo_images": [
                    item for item in list_data["listImages"] if is_meaningful_alt(item.get("alt"))
                ],
            },
            "detail_page": {
                "url": page.url,
                "images": detail_images,
                "seo_images": [
                    item for item in detail_images if is_meaningful_alt(item.get("alt"))
                ],
            },
        }

        print(json.dumps(result, ensure_ascii=False, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
