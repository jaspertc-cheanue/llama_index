"""OpenAI Finetuning."""

from llama_index.finetuning.types import BaseFinetuningEngine
from llama_index.callbacks import OpenAIFineTuningHandler
from llama_index.finetuning.openai.validate_json import validate_json
from typing import Any, Optional
import os
import openai
from llama_index.llms import OpenAI
import time
import logging

from llama_index.llms.base import LLM

logger = logging.getLogger(__name__)


class OpenAIFinetuneEngine(BaseFinetuningEngine):
    """OpenAI Finetuning Engine."""

    def __init__(
        self,
        base_model: str,
        data_path: str,
        verbose: bool = False,
        start_job_id: Optional[str] = None,
    ) -> None:
        """Init params."""
        self.base_model = base_model
        self.data_path = data_path
        self._verbose = verbose
        self._start_job: Optional[Any] = None
        if start_job_id is not None:
            self._start_job = openai.FineTuningJob.retrieve(start_job_id)

    @classmethod
    def from_finetuning_handler(
        cls,
        finetuning_handler: OpenAIFineTuningHandler,
        base_model: str,
        data_path: str,
        **kwargs: Any,
    ) -> "OpenAIFinetuneEngine":
        """Initialize from finetuning handler.

        Used to finetune an OpenAI model into another
        OpenAI model (e.g. gpt-3.5-turbo on top of GPT-4).

        """
        finetuning_handler.save_finetuning_events(data_path)
        return cls(base_model=base_model, data_path=data_path, **kwargs)

    def finetune(self) -> None:
        """Finetune model."""
        validate_json(self.data_path)

        file_name = os.path.basename(self.data_path)

        # upload file
        with open(self.data_path, "rb") as f:
            output = openai.File.create(
                file=f,
                purpose="fine-tune",
                user_provided_filename=file_name,
            )
        logger.info("File uploaded...")
        if self._verbose:
            print("File uploaded...")

        # launch training
        while True:
            try:
                job_output = openai.FineTuningJob.create(
                    training_file=output["id"], model=self.base_model
                )
                self._start_job = job_output
                break
            except openai.error.InvalidRequestError:
                print("Waiting for file to be ready...")
                time.sleep(60)
        info_str = (
            f"Training job {output['id']} launched. "
            "You will be emailed when it's complete."
        )
        logger.info(info_str)
        if self._verbose:
            print(info_str)

    def get_current_job(self) -> Any:
        """Get current job."""
        # validate that it works
        if not self._start_job:
            raise ValueError("Must call finetune() first")

        # try getting id, make sure that run succeeded
        job_id = self._start_job["id"]
        current_job = openai.FineTuningJob.retrieve(job_id)
        return current_job

    def get_finetuned_model(self, **model_kwargs: Any) -> LLM:
        """Gets finetuned model."""
        current_job = self.get_current_job()

        job_id = current_job["id"]
        status = current_job["status"]
        model_id = current_job["fine_tuned_model"]

        if model_id is None:
            raise ValueError(
                f"Job {job_id} does not have a finetuned model id ready yet."
            )
        if status != "succeeded":
            raise ValueError(f"Job {job_id} has status {status}, cannot get model")

        llm = OpenAI(model=model_id, **model_kwargs)
        return llm
