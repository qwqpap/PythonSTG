"""完整代码驱动关卡编辑器示例。"""

from src.authoring.dsl import Project, Ref


project = Project(
    id="code_editor_demo",
    name="代码驱动编辑器完整示例",
    start_stage=Ref("demo_stage"),
    stages=[Ref("demo_stage")],
)
