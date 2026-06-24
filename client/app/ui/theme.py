"""
温暖拟人化主题：调色板（珊瑚粉/暖橙/米白）+ 全局 QSS 样式表。
圆润、柔和、有温度，区别于冷工具向 UI。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M5 创建温暖拟人化主题（调色板 + QSS）
"""
# 调色板
PRIMARY = "#FF8B7B"            # 珊瑚粉（主色：用户气泡/按钮/强调）
PRIMARY_DARK = "#E8796A"       # 主色按下/悬停
ACCENT = "#FFB366"             # 暖橙（点缀）
BG = "#FAF7F2"                 # 米白（窗口背景）
BG_PANEL = "#FFFFFF"           # 面板/输入框背景
BG_BUBBLE_AI = "#FFFFFF"       # AI 气泡背景
BG_BUBBLE_USER = "#FF8B7B"     # 用户气泡背景（主色）
TEXT = "#3A3A3A"               # 正文
TEXT_ON_PRIMARY = "#FFFFFF"    # 主色上的文字
TEXT_MUTED = "#9A9A9A"         # 次要/系统提示
BORDER = "#ECE6DE"             # 分隔/边框
BUBBLE_RADIUS = 14             # 气泡圆角

# 全局 QSS
QSS = f"""
QMainWindow, QWidget {{
    background: {BG}; color: {TEXT};
    font-family: "Microsoft YaHei", "SimHei", "Segoe UI", sans-serif; font-size: 14px;
}}
QPushButton#sendBtn {{
    background: {PRIMARY}; color: {TEXT_ON_PRIMARY}; border: none;
    border-radius: 16px; padding: 7px 20px; font-weight: 600;
}}
QPushButton#sendBtn:hover {{ background: {PRIMARY_DARK}; }}
QPushButton#sendBtn:disabled {{ background: #D8D2CB; color: {TEXT_ON_PRIMARY}; }}
QPushButton#iconBtn {{ background: transparent; border: none; font-size: 18px; padding: 4px 8px; }}
QPushButton#iconBtn:hover {{ color: {PRIMARY}; }}
QLineEdit, QTextEdit {{
    background: {BG_PANEL}; border: 1px solid {BORDER};
    border-radius: 18px; padding: 8px 14px;
}}
QLineEdit:focus {{ border: 1px solid {PRIMARY}; }}
QScrollArea {{ border: none; background: transparent; }}
QFrame#topBar {{ background: {BG_PANEL}; border-bottom: 1px solid {BORDER}; }}
QFrame#drawer {{ background: {BG_PANEL}; border-right: 1px solid {BORDER}; }}
QLabel#bubbleAI {{
    background: {BG_BUBBLE_AI}; color: {TEXT}; border: 1px solid {BORDER};
    border-radius: {BUBBLE_RADIUS}px; padding: 8px 12px;
}}
QLabel#bubbleUser {{
    background: {BG_BUBBLE_USER}; color: {TEXT_ON_PRIMARY};
    border-radius: {BUBBLE_RADIUS}px; padding: 8px 12px;
}}
QLabel#bubbleSys {{ color: {TEXT_MUTED}; font-size: 12px; }}
QLabel#title {{ font-size: 15px; font-weight: 600; }}
QLabel#muted {{ color: {TEXT_MUTED}; font-size: 12px; }}
QListWidget {{ border: none; background: transparent; outline: none; }}
QListWidget::item {{ padding: 6px 4px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {PRIMARY}; color: {TEXT_ON_PRIMARY}; }}
"""
