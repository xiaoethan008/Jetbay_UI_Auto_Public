from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


def get_screen_size() -> tuple[int, int]:
    """获取当前机器屏幕分辨率，失败时返回默认值。"""
    try:
        import tkinter as tk

        root = tk.Tk()
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        root.destroy()
        return screen_width, screen_height
    except Exception:
        return 1920, 1080


def wait_for_render_frames(page, frames: int = 2):
    """等待浏览器完成指定数量的渲染帧，不依赖固定毫秒睡眠。"""
    page.evaluate(
        """
        async (frameCount) => {
            for (let index = 0; index < frameCount; index += 1) {
                await new Promise((resolve) => requestAnimationFrame(resolve));
            }
        }
        """,
        max(frames, 1),
    )


def scroll_page_for_lazy_content(page, steps: int = 6, delta_y: int = 1400):
    """分段滚动触发懒加载；每步仅等待浏览器渲染帧。"""
    page.wait_for_load_state("domcontentloaded")
    for _ in range(steps):
        page.mouse.wheel(0, delta_y)
        wait_for_render_frames(page)
    page.mouse.wheel(0, -10000)
    wait_for_render_frames(page)


def wait_for_image_loaded(image, timeout: int = 5000) -> bool:
    """等待图片节点完成解码并具有有效自然宽度。"""
    try:
        handle = image.element_handle(timeout=timeout)
        if handle is None:
            return False
        image.page.wait_for_function(
            "(el) => Boolean(el && el.complete && el.naturalWidth > 0)",
            arg=handle,
            timeout=timeout,
        )
        return True
    except PlaywrightTimeoutError:
        return False
    except Exception:
        return False
