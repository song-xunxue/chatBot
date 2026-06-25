"""
桌宠窗口测试（offscreen）：默认狐狸 SVG 渲染、抖动动画、切换/退出回调接线。

作者: 李文煜
日期: 2026-06-24

2026-06-24
变更说明：
  1. M6.1 覆盖 PetWindow：渲染/shake/回调
"""


def test_pet_renders_default_fox(qapp):
    """无 REST/无上传 → 渲染内置 fox.svg，pixmap 非空"""
    from ui.pet_window import PetWindow
    pet = PetWindow(on_toggle_chat=lambda: None, on_quit=lambda: None, rest=None)
    qapp.processEvents()
    pm = pet.label.pixmap()
    assert pm is not None and not pm.isNull()


def test_pet_shake_creates_animation(qapp):
    from ui.pet_window import PetWindow
    pet = PetWindow(on_toggle_chat=lambda: None, on_quit=lambda: None)
    pet.shake()
    qapp.processEvents()
    assert pet._shake_anim is not None


def test_pet_callbacks_wired(qapp):
    """on_toggle_chat / on_quit 可调用且被正确保存"""
    from ui.pet_window import PetWindow
    flag = {"t": 0, "q": 0}
    pet = PetWindow(on_toggle_chat=lambda: flag.__setitem__("t", 1),
                    on_quit=lambda: flag.__setitem__("q", 1))
    pet._on_toggle()
    pet._on_quit()
    assert flag == {"t": 1, "q": 1}
