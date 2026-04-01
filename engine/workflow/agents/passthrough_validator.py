from engine.interfaces.workflow import ValidationResponse, ValidatorContext


class PassthroughValidator:
    def validate(self, goal: str, context: ValidatorContext) -> ValidationResponse:
        return ValidationResponse(passed=True, verdict="all steps passed")
