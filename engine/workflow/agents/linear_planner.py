from engine.interfaces.workflow import PlannerContext, PlanResponse, PlanStep


class LinearPlanner:
    def __init__(self, steps: list[PlanStep]) -> None:
        self._steps = steps

    def plan(self, goal: str, context: PlannerContext) -> PlanResponse:
        return PlanResponse(steps=self._steps, rationale="linear plan")
