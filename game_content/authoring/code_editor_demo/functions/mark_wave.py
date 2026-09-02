from src.authoring.dsl import Expr, Function, Parameter, Set


function = Function(
    id="mark_wave",
    name="记录当前 Wave",
    parameters=[Parameter("label", "str")],
    body=[
        Set("wave_label", Expr("label"), uid="mark_wave_value"),
    ],
)
