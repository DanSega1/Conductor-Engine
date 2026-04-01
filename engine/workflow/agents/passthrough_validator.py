from engine.interfaces.workflow import ValidationResponse, ValidatorContext, ValidatorInterface


class PassthroughValidator(ValidatorInterface):
    def validate(self, goal: str, context: ValidatorContext) -> ValidationResponse:
        return ValidationResponse(passed=True, verdict="all steps passed")
