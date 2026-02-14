"""
简化对话文本渲染器 - 用于快速测试

在屏幕中央显示对话文本，无需复杂的气泡和立绘。
后续可以替换为完整的 DialogRenderer。
"""

import pygame
from typing import Optional
from .dialog_data import DialogSentence


class SimpleDialogTextRenderer:
    """简化对话文本渲染器 - 只显示文字"""

    def __init__(self, screen_width: int = 640, screen_height: int = 480):
        self.screen_width = screen_width
        self.screen_height = screen_height

        # 当前显示的句子
        self.current_sentence: Optional[DialogSentence] = None
        self.visible_chars: int = 0  # 打字机效果
        self.frame_counter: int = 0

        # 字体
        try:
            self.font = pygame.font.Font(None, 32)  # 默认字体
            self.name_font = pygame.font.Font(None, 24)
        except:
            self.font = None
            self.name_font = None

    def set_sentence(self, sentence: DialogSentence):
        """设置要显示的句子"""
        self.current_sentence = sentence
        self.visible_chars = 0
        self.frame_counter = 0

    def update(self):
        """更新打字机效果"""
        if not self.current_sentence:
            return

        self.frame_counter += 1

        # 每3帧显示一个字符
        if self.frame_counter % 3 == 0:
            if self.visible_chars < len(self.current_sentence.text):
                self.visible_chars += 1

    def render(self, screen: pygame.Surface):
        """渲染对话文本"""
        if not self.current_sentence or not self.font:
            return

        # 背景半透明遮罩
        overlay = pygame.Surface((self.screen_width, 200))
        overlay.set_alpha(180)
        overlay.fill((0, 0, 0))
        screen.blit(overlay, (0, self.screen_height - 200))

        # 角色名字
        if self.current_sentence.character:
            name_text = self.current_sentence.character
            if self.name_font:
                name_surface = self.name_font.render(name_text, True, (255, 255, 100))
                screen.blit(name_surface, (20, self.screen_height - 190))

        # 对话文本（带打字机效果）
        visible_text = self.current_sentence.text[:self.visible_chars]

        if self.font:
            # 多行处理
            lines = self._wrap_text(visible_text, self.font, self.screen_width - 40)

            y_offset = self.screen_height - 150
            for line in lines:
                text_surface = self.font.render(line, True, (255, 255, 255))
                screen.blit(text_surface, (20, y_offset))
                y_offset += 35

        # 提示文本（对话完成后显示）
        if self.visible_chars >= len(self.current_sentence.text):
            hint_text = "[按 Z 继续]"
            if self.name_font:
                hint_surface = self.name_font.render(hint_text, True, (200, 200, 200))
                screen.blit(hint_surface, (self.screen_width - 150, self.screen_height - 30))

    def _wrap_text(self, text: str, font, max_width: int):
        """简单的文本换行"""
        words = text
        lines = []
        current_line = ""

        for char in words:
            test_line = current_line + char
            if font.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = char

        if current_line:
            lines.append(current_line)

        return lines

    def clear(self):
        """清空显示"""
        self.current_sentence = None
        self.visible_chars = 0
        self.frame_counter = 0
