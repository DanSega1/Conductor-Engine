from engine.interfaces.task import TaskSubmission
from engine.interfaces.workflow import WorkerContext, WorkerResponse


class PassthroughWorker:
    def work(self, step_name: str, context: WorkerContext) -> WorkerResponse:
        submission = TaskSubmission(
            name=step_name,
            capability=context.step.capability,
            input=context.step.input_hint,
            workflow_id=context.workflow_id,
        )
        return WorkerResponse(submission=submission)
