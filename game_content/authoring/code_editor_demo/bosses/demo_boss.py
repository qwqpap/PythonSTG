from src.authoring.dsl import Boss, Ref


boss = Boss(
    id="demo_boss",
    name="露米娅（编辑器演示）",
    texture="sunny",
    phases=[Ref("demo_nonspell"), Ref("demo_spell")],
)
