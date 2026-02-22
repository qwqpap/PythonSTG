"""
主菜单编辑器 - 入口与主循环

独立窗口：glfw + ModernGL + imgui
左侧 imgui 面板（元素列表 + 属性），右侧主菜单预览。
"""

import sys
import os

# 添加项目根目录以便导入 src
root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, root)
os.chdir(root)

import glfw
import moderngl
import numpy as np
import imgui

from .imgui_bridge import create_glfw_renderer, frame_begin, frame_end
from .layout_model import default_layout, load_layout, save_layout
from src.ui.main_menu_renderer import MainMenuRenderer


# 预览分辨率（与游戏一致）
PREVIEW_W = 384
PREVIEW_H = 448
# 编辑器窗口
EDITOR_W = 1000
EDITOR_H = 700
# 左侧面板宽度
PANEL_W = 300


def _ensure_list3(val):
    if isinstance(val, (list, tuple)) and len(val) >= 3:
        return [float(val[0]), float(val[1]), float(val[2])]
    return [255, 255, 255]


def _draw_element_list(layout: dict, selected_key: str) -> str:
    """绘制元素列表，返回新选中的 key。"""
    keys = ["title"]
    options = layout.get("options", [])
    for i in range(len(options)):
        keys.append(f"option_{i}")
    keys.append("options")
    keys.append("hint")
    keys.append("bg")

    for k in keys:
        label = {"title": "标题", "hint": "提示", "bg": "背景", "options": "选项通用"}.get(k, k)
        if k.startswith("option_"):
            idx = int(k.split("_")[1])
            opt = options[idx] if idx < len(options) else {}
            text = opt.get("text", "") if isinstance(opt, dict) else str(opt)
            label = f"选项 {idx + 1}: {text[:8]}..."
        clicked, _ = imgui.selectable(label, selected_key == k)
        if clicked:
            selected_key = k
    return selected_key


def _draw_property_panel(layout: dict, selected_key: str) -> None:
    """根据选中的 key 绘制属性面板。"""
    if selected_key == "title":
        cfg = layout.setdefault("title", {})
        cfg["text"] = cfg.get("text", "弹幕游戏")
        _, cfg["text"] = imgui.input_text("文本", cfg["text"], 256)
        _, cfg["font_size"] = imgui.slider_int("字号", int(cfg.get("font_size", 56)), 12, 120)
        c = _ensure_list3(cfg.get("color", [220, 220, 255]))
        changed, c_out = imgui.color_edit3("颜色", c[0] / 255, c[1] / 255, c[2] / 255)
        if changed:
            cfg["color"] = [int(c_out[0] * 255), int(c_out[1] * 255), int(c_out[2] * 255)]
        _, cfg["y_ratio"] = imgui.slider_float("Y 比例", float(cfg.get("y_ratio", 0.25)), 0.0, 1.0)

    elif selected_key.startswith("option_"):
        idx = int(selected_key.split("_")[1])
        options = layout.setdefault("options", [])
        while len(options) <= idx:
            options.append({"text": ""})
        opt = options[idx]
        if not isinstance(opt, dict):
            opt = {"text": str(opt)}
            options[idx] = opt
        _, opt["text"] = imgui.input_text("文本", opt.get("text", "") or "", 128)

        if imgui.button("删除此选项") and len(options) > 1:
            options.pop(idx)

    elif selected_key == "options":
        _, layout["option_spacing"] = imgui.slider_int("选项间距", int(layout.get("option_spacing", 48)), 8, 120)
        colors = layout.setdefault("option_colors", {"normal": [160, 160, 180], "selected": [255, 255, 200]})
        cn = _ensure_list3(colors.get("normal", [160, 160, 180]))
        changed, cn_out = imgui.color_edit3("未选中颜色", cn[0] / 255, cn[1] / 255, cn[2] / 255)
        if changed:
            colors["normal"] = [int(cn_out[0] * 255), int(cn_out[1] * 255), int(cn_out[2] * 255)]
        cs = _ensure_list3(colors.get("selected", [255, 255, 200]))
        changed, cs_out = imgui.color_edit3("选中颜色", cs[0] / 255, cs[1] / 255, cs[2] / 255)
        if changed:
            colors["selected"] = [int(cs_out[0] * 255), int(cs_out[1] * 255), int(cs_out[2] * 255)]

        if imgui.button("添加选项"):
            layout.setdefault("options", []).append({"text": "新选项"})

    elif selected_key == "hint":
        cfg = layout.setdefault("hint", {})
        _, cfg["text"] = imgui.input_text("文本", cfg.get("text", "") or "", 256)
        _, cfg["font_size"] = imgui.slider_int("字号", int(cfg.get("font_size", 18)), 8, 48)
        c = _ensure_list3(cfg.get("color", [100, 100, 120]))
        changed, c_out = imgui.color_edit3("颜色", c[0] / 255, c[1] / 255, c[2] / 255)
        if changed:
            cfg["color"] = [int(c_out[0] * 255), int(c_out[1] * 255), int(c_out[2] * 255)]
        _, cfg["y_offset"] = imgui.slider_int("Y 偏移", int(cfg.get("y_offset", -50)), -200, 200)

    elif selected_key == "bg":
        bg = layout.setdefault("bg_gradient", {"top": [12, 8, 28], "bottom": [20, 20, 44]})
        t = _ensure_list3(bg.get("top", [12, 8, 28]))
        changed, t_out = imgui.color_edit3("顶部颜色", t[0] / 255, t[1] / 255, t[2] / 255)
        if changed:
            bg["top"] = [int(t_out[0] * 255), int(t_out[1] * 255), int(t_out[2] * 255)]
        b = _ensure_list3(bg.get("bottom", [20, 20, 44]))
        changed, b_out = imgui.color_edit3("底部颜色", b[0] / 255, b[1] / 255, b[2] / 255)
        if changed:
            bg["bottom"] = [int(b_out[0] * 255), int(b_out[1] * 255), int(b_out[2] * 255)]


def _create_blit_program(ctx: moderngl.Context):
    """创建用于将纹理绘制到当前 viewport 的简单程序。"""
    vs = """
    #version 330
    in vec2 in_pos;
    in vec2 in_uv;
    out vec2 v_uv;
    void main() {
        gl_Position = vec4(in_pos * 2.0 - 1.0, 0.0, 1.0);
        v_uv = in_uv;
    }
    """
    fs = """
    #version 330
    uniform sampler2D u_tex;
    in vec2 v_uv;
    out vec4 f_color;
    void main() {
        f_color = texture(u_tex, vec2(v_uv.x, 1.0 - v_uv.y));
    }
    """
    prog = ctx.program(vertex_shader=vs, fragment_shader=fs)
    # 全屏四边形 (0,0)-(1,1)
    vertices = np.array([
        0, 0, 0, 1,
        0, 1, 0, 0,
        1, 0, 1, 1,
        1, 0, 1, 1,
        0, 1, 0, 0,
        1, 1, 1, 0,
    ], dtype='f4')
    vbo = ctx.buffer(vertices.tobytes())
    vao = ctx.vertex_array(prog, [(vbo, '2f 2f', 'in_pos', 'in_uv')])
    return prog, vao


def run_editor():
    """运行主菜单编辑器。"""
    if not glfw.init():
        raise RuntimeError("glfw.init failed")

    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, True)
    glfw.window_hint(glfw.RESIZABLE, True)

    window = glfw.create_window(EDITOR_W, EDITOR_H, "主菜单编辑器", None, None)
    if not window:
        glfw.terminate()
        raise RuntimeError("glfw.create_window failed")

    glfw.make_context_current(window)
    ctx = moderngl.create_context()

    ctx.enable(moderngl.BLEND)
    ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

    # 预览 FBO
    preview_tex = ctx.texture((PREVIEW_W, PREVIEW_H), 4)
    preview_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
    fbo = ctx.framebuffer(preview_tex)

    menu_renderer = MainMenuRenderer(ctx, PREVIEW_W, PREVIEW_H)
    blit_prog, blit_vao = _create_blit_program(ctx)

    imgui.create_context()
    io = imgui.get_io()
    font_path = os.path.join(root, "assets", "fonts", "SourceHanSansCN-Bold.otf")
    if not os.path.exists(font_path):
        font_path = os.path.join(root, "assets", "fonts", "wqy-microhei-mono.ttf")
    if os.path.exists(font_path):
        io.fonts.clear()
        glyph_ranges = io.fonts.get_glyph_ranges_chinese_full()
        io.fonts.add_font_from_file_ttf(font_path, 18, glyph_ranges=glyph_ranges)

    impl = create_glfw_renderer(window)
    if os.path.exists(font_path):
        impl.refresh_font_texture()

    layout = default_layout()
    selected_key = "title"
    selected_index = 0

    def render_preview():
        fbo.use()
        ctx.clear(0.1, 0.1, 0.15)
        menu_renderer.render_from_layout(layout, selected_index)

    def blit_preview_to_screen(x: int, y: int, w: int, h: int):
        ctx.screen.use()
        ctx.viewport = (x, y, w, h)
        preview_tex.use(0)
        blit_prog['u_tex'].value = 0
        blit_vao.render(moderngl.TRIANGLES)

    while not glfw.window_should_close(window):
        glfw.poll_events()
        frame_begin(impl)

        # 渲染主菜单到 FBO
        render_preview()

        # 切换到默认 framebuffer，清屏
        ctx.screen.use()
        fw, fh = glfw.get_framebuffer_size(window)
        ctx.viewport = (0, 0, fw, fh)
        ctx.clear(0.15, 0.15, 0.2)

        # 将预览绘制到右侧
        blit_preview_to_screen(PANEL_W, 0, max(1, fw - PANEL_W), fh)

        # 左侧 imgui 面板
        imgui.set_next_window_position(0, 0)
        imgui.set_next_window_size(float(PANEL_W), float(fh))
        imgui.begin("主菜单编辑器", flags=imgui.WINDOW_NO_RESIZE | imgui.WINDOW_NO_COLLAPSE)

        # 工具栏
        if imgui.button("保存"):
            save_layout(layout)
        imgui.same_line()
        if imgui.button("加载"):
            layout = load_layout()
        imgui.same_line()
        if imgui.button("重置"):
            layout = default_layout()
        imgui.separator()

        imgui.text("元素列表")
        selected_key = _draw_element_list(layout, selected_key)
        imgui.separator()

        imgui.text("属性")
        imgui.begin_child("props", 0, -60)
        _draw_property_panel(layout, selected_key)
        imgui.end_child()

        imgui.separator()
        imgui.text("预览选中项:")
        num_opts = max(1, len(layout.get("options", [])))
        _, selected_index = imgui.slider_int("##sel", selected_index, 0, num_opts - 1)

        imgui.end()

        frame_end(impl)
        glfw.swap_buffers(window)

    impl.shutdown()
    menu_renderer.cleanup()
    fbo.release()
    preview_tex.release()
    blit_vao.release()
    blit_prog.release()
    glfw.destroy_window(window)
    glfw.terminate()


if __name__ == "__main__":
    run_editor()
