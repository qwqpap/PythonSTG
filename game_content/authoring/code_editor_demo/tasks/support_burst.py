from src.authoring.dsl import Expr, FireCircle, Parameter, Repeat, Task, Wait


task = Task(
    id="support_burst",
    name="参数化支援环射",
    parameters=[
        Parameter("bursts", "int", 2),
        Parameter("interval", "int", 15),
    ],
    body=[
        Repeat(
            Expr("bursts"),
            body=[
                FireCircle(
                    x=0.0,
                    y=0.75,
                    count=12,
                    speed=1.4,
                    uid="support_fire",
                ),
                Wait(Expr("interval"), uid="support_wait"),
            ],
            uid="support_repeat",
        )
    ],
)
