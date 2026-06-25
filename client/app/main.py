"""
MyChat 客户端入口（M5 桌面核心 + M6.1 桌宠）
温暖拟人化主题 + 单列聊天 + 抽屉布局；桌宠悬浮桌面，点击切换聊天窗，
收到主动消息 nudge 时抖动；关闭聊天窗缩到桌宠，托盘退出。

作者: 李文煜
日期: 2026-06-15

2026-06-15
变更说明：
  1. M1.3 创建最小应用：主窗口占位 + 系统托盘
  2. M1.5 接入 WebSocket：输入框/发送/消息显示，打通端到端 tracer bullet

2026-06-24
变更说明：
  1. M5 重写为桌面核心：主题化主窗口(气泡/流式/抽屉) + 自动重连 + SQLite 缓存 + 离线补发
  2. M6.1 加入桌宠 PetWindow：白色悬浮窗 + 点击切换 + nudge 抖动 + 关闭缩到桌宠
"""
import logging
import sys

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from config import load_config
from net.rest_client import RestClient
from ui.theme import QSS
from ui.main_window import MainWindow
from ui.pet_window import PetWindow


def main():
    """客户端入口"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)                      # 温暖拟人化主题

    cfg = load_config()
    rest = RestClient(cfg.rest_url, cfg.token)

    # 1.聊天主窗口（先建，桌宠的切换回调需要引用它）
    win = MainWindow(cfg)

    # 2.桌宠：白色小狐狸悬浮窗
    def toggle_chat():
        if win.isVisible():
            win.hide()
        else:
            win.show()
            win.raise_()
            win.activateWindow()

    def do_quit():
        win.real_close()
        app.quit()

    pet = PetWindow(on_toggle_chat=toggle_chat, on_quit=do_quit, rest=rest)
    win.pet = pet                                # 注入：nudge→抖动 / 关闭→缩到桌宠
    pet.move(120, 120)
    pet.show()
    win.show()

    # 3.系统托盘（桌宠是主要入口，托盘作为退出/兜底）
    tray = QSystemTrayIcon(app)
    tray.setIcon(app.style().standardIcon(QStyle.SP_ComputerIcon))
    tray.setToolTip("MyChat · 浔")
    menu = QMenu()
    act_show = QAction("显示/隐藏聊天")
    act_show.triggered.connect(toggle_chat)
    act_quit = QAction("退出")
    act_quit.triggered.connect(do_quit)
    menu.addAction(act_show)
    menu.addAction(act_quit)
    tray.setContextMenu(menu)
    tray.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
