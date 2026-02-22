"""
imgui + glfw 封装

负责 imgui 上下文创建、每帧 process_events / new_frame / render。
"""

import imgui
from imgui.integrations.glfw import GlfwRenderer


def create_imgui_context():
    """创建 imgui 上下文并返回。"""
    imgui.create_context()
    return imgui.get_io()


def create_glfw_renderer(glfw_window) -> GlfwRenderer:
    """
    创建 GlfwRenderer，用于处理 imgui 的输入和 GL 渲染。

    Args:
        glfw_window: glfw 窗口句柄 (from glfw.create_window)
    """
    return GlfwRenderer(glfw_window)


def frame_begin(impl: GlfwRenderer):
    """每帧开始：处理输入，new_frame。"""
    impl.process_inputs()
    imgui.new_frame()


def frame_end(impl: GlfwRenderer):
    """每帧结束：render imgui，绘制到当前 framebuffer。"""
    imgui.render()
    impl.render(imgui.get_draw_data())
