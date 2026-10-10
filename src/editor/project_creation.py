"""Create the two source files needed for a first playable authoring project."""

from __future__ import annotations

import keyword
import shutil
import tempfile
from pathlib import Path

from src.authoring import dsl
from src.authoring.program import AuthoringProgram, Ref
from src.authoring.python_source import AuthoringSourceProject
from src.core.project_context import ProjectContext
from src.qt_compat.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from .starter_content import make_starter_wave


def create_authoring_project(
    runtime_root: Path, project_id: str, name: str, *, include_starter: bool = False
) -> Path:
    """Persist a Project and its first Stage using the normal source writer."""

    if not project_id.isidentifier() or keyword.iskeyword(project_id):
        raise ValueError("工程 ID 必须是有效的 Python 名称，例如 my_game。")
    if not name.strip():
        raise ValueError("请填写工程名称。")
    context = ProjectContext.discover(runtime_root)
    destination = context.game_content / "authoring" / project_id
    if destination.exists():
        raise FileExistsError(f"工程 {project_id} 已存在，请换一个 ID。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="_creating_project_", dir=destination.parent))
    try:
        source = AuthoringSourceProject(staging, {}, AuthoringProgram())
        stage_id = "stage1" if project_id != "stage1" else "opening_stage"
        stage_body = [dsl.Wait(60)]
        if include_starter:
            enemy, wave = make_starter_wave({project_id, stage_id})
            source.add_unsaved_unit(enemy, f"enemies/{enemy.id}.py")
            source.add_unsaved_unit(wave, f"waves/{wave.id}.py")
            stage_body = [dsl.Wait(30), dsl.RunWave(Ref(wave.id)), dsl.Wait(90)]
        source.add_unsaved_unit(
            dsl.Stage(stage_id, "第一关", body=stage_body), f"stages/{stage_id}.py"
        )
        source.add_unsaved_unit(
            dsl.Project(project_id, name.strip(), Ref(stage_id), [Ref(stage_id)]),
            "project.py",
        )
        for unit in source.program.logical_units():
            source.save_unit(unit.id)
        staging.rename(destination)
    except Exception:
        shutil.rmtree(staging)
        raise
    return destination


class NewProjectDialog(QDialog):
    def __init__(self, runtime_root: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("新建关卡工程")
        self.setMinimumWidth(480)
        form = QFormLayout(self)
        project_id = "my_game"
        index = 2
        while (runtime_root / "game_content" / "authoring" / project_id).exists():
            project_id = f"my_game_{index}"
            index += 1
        self.project_id = QLineEdit(project_id, self)
        self.project_id.setObjectName("new_project_id")
        self.name = QLineEdit("新工程", self)
        self.name.setObjectName("new_project_name")
        self.runtime_root = QLineEdit(str(runtime_root), self)
        self.runtime_root.setReadOnly(True)
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.runtime_root)
        choose = QPushButton("选择…", row)
        choose.clicked.connect(self._choose_runtime)
        layout.addWidget(choose)
        form.addRow("工程文件夹", self.project_id)
        form.addRow("工程名称", self.name)
        self.include_starter = QCheckBox("附带环形弹幕入门示例（推荐）", self)
        self.include_starter.setObjectName("new_project_include_starter")
        self.include_starter.setChecked(True)
        form.addRow(self.include_starter)
        form.addRow("PySTG 运行目录", row)
        hint = QLabel(
            "将在运行目录的 game_content/authoring/ 下建立工程，"
            "入门示例已连接好关卡、敌人和发射步骤，可直接改参数运行。"
            "取消勾选可从空白关卡开始。", self
        )
        hint.setWordWrap(True)
        form.addRow(hint)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("创建工程")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _choose_runtime(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "选择 PySTG 运行目录", self.runtime_root.text()
        )
        if selected:
            self.runtime_root.setText(selected)

    def values(self) -> tuple[Path, str, str]:
        return (
            Path(self.runtime_root.text()),
            self.project_id.text().strip(),
            self.name.text().strip(),
        )
