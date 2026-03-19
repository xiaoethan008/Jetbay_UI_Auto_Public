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
