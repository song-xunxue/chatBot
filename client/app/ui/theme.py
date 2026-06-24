"""
微信/QQ 风格主题：调色板 + 全局 QSS 样式表。
聊天区主背景灰、列表/顶栏浅灰、用户气泡微信绿、AI 气泡白；字体层次分明。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M5 创建温暖拟人化主题（调色板 + QSS）

2026-06-25
变更说明：
  1. 重构为微信/QQ 风格：微信绿用户气泡 + 白 AI 气泡、列表项选中/hover、字体层次、统一图标按钮
"""
# 调色板（微信风格）
BG_CHAT = "#EDEDED"             # 聊天区主背景
BG_PANEL = "#F5F5F5"            # 左列表/顶栏背景
BG_PANEL_ALT = "#F7F7F7"        # 备用面板底
BG_INPUT = "#FFFFFF"            # 输入框/气泡白底
BG_BUBBLE_AI = "#FFFFFF"        # AI 气泡背景
BG_BUBBLE_USER = "#95EC69"      # 用户气泡背景（微信绿）
BG_ITEM_SELECTED = "#D6D6D6"    # 列表选中项
BG_ITEM_HOVER = "#ECECEC"       # 列表 hover
TEXT = "#1A1A1A"                # 主文字
TEXT_MUTED = "#999999"          # 次要/时间/状态
BORDER = "#E0E0E0"              # 分隔线
BORDER_LIGHT = "#ECECEC"        # 细分隔线（列表项之间）
USER_GREEN = "#95EC69"
AVATAR_SIZE = 40                # 头像尺寸（列表/气泡统一）
BUBBLE_RADIUS = 6               # 气泡圆角（微信式较小圆角）

# 全局 QSS
QSS = f"""
QMainWindow, QWidget {{
    background: {BG_CHAT}; color: {TEXT};
    font-family: "Microsoft YaHei", "SimHei", "Segoe UI", sans-serif; font-size: 13px;
}}
/* —— 顶栏 —— */
QFrame#topBar {{
    background: {BG_PANEL}; border-bottom: 1px solid {BORDER};
}}
/* —— 左对象列表面板 —— */
QFrame#objectPanel {{
    background: {BG_PANEL}; border-right: 1px solid {BORDER};
}}
QLabel#panelHead {{
    background: {BG_PANEL}; color: {TEXT_MUTED};
    font-size: 12px; padding-left: 12px;
    border-bottom: 1px solid {BORDER_LIGHT};
}}
QLabel#title {{ font-size: 14px; font-weight: 600; color: {TEXT}; }}
QLabel#muted, QLabel#status {{ color: {TEXT_MUTED}; font-size: 11px; }}
QLabel#bubbleSys {{ color: {TEXT_MUTED}; font-size: 11px; }}
/* —— QListWidget 列表项（选中/hover） —— */
QListWidget {{
    border: none; background: {BG_PANEL}; outline: none;
    font-size: 14px;
}}
QListWidget::item {{
    border-bottom: 1px solid {BORDER_LIGHT};
    padding: 6px 8px;
}}
QListWidget::item:hover {{ background: {BG_ITEM_HOVER}; }}
QListWidget::item:selected {{ background: {BG_ITEM_SELECTED}; color: {TEXT}; }}
/* —— 气泡（QFrame，微信式小圆角） —— */
QFrame#bubbleAI {{
    background: {BG_BUBBLE_AI}; color: {TEXT};
    border: 1px solid {BORDER_LIGHT};
    border-radius: {BUBBLE_RADIUS}px;
}}
QFrame#bubbleUser {{
    background: {BG_BUBBLE_USER}; color: {TEXT};
    border: none; border-radius: {BUBBLE_RADIUS}px;
}}
/* 气泡内内容 QLabel */
QLabel#bubbleContentAI, QLabel#bubbleContentUser {{ font-size: 13px; }}
/* —— 输入栏 —— */
QFrame#inputBar {{
    background: {BG_PANEL}; border-top: 1px solid {BORDER};
}}
QLineEdit, QTextEdit {{
    background: {BG_INPUT}; border: 1px solid {BORDER};
    border-radius: 4px; padding: 6px 10px; font-size: 13px;
}}
QLineEdit:focus {{ border: 1px solid {USER_GREEN}; }}
/* —— 按钮（统一） —— */
QPushButton#sendBtn {{
    background: {USER_GREEN}; color: {TEXT}; border: none;
    border-radius: 4px; padding: 6px 18px; font-weight: 600; font-size: 13px;
}}
QPushButton#sendBtn:hover {{ background: #7BD65A; }}
QPushButton#sendBtn:disabled {{ background: #C8C8C8; color: {TEXT_MUTED}; }}
QPushButton#iconBtn {{
    background: transparent; border: none; padding: 4px;
}}
QPushButton#iconBtn:hover {{ background: {BG_ITEM_HOVER}; border-radius: 4px; }}
QPushButton#meBtn {{
    background: transparent; border: none; padding: 2px;
}}
QPushButton#meBtn:hover {{ background: {BG_ITEM_HOVER}; border-radius: 4px; }}
QScrollArea {{ border: none; background: {BG_CHAT}; }}
"""
