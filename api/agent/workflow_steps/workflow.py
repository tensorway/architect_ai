from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from agent.logging.workflow_utils import (
    enter_step,
    exit_step,
    generate_step_uuid,
    log_step,
)

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class WorkflowStep(ABC, Generic[InputT, OutputT]):

    @abstractmethod
    def _run(self, input: InputT) -> OutputT: ...

    def run(self, input: InputT) -> OutputT:
        self._workflow_step_uuid = generate_step_uuid()
        caller_uuid, token = enter_step(self._workflow_step_uuid)
        try:
            output = self._run(input)
            self._log(caller_uuid, input, output)
            return output
        finally:
            exit_step(token)

    def _log(
        self, caller_uuid: str | None, input_value: InputT, output_value: OutputT
    ) -> None:
        log_step(
            step_uuid=self._workflow_step_uuid,
            caller_uuid=caller_uuid,
            step_class=self.__class__.__name__,
            step_module=self.__class__.__module__,
            input_value=input_value,
            output_value=output_value,
        )
