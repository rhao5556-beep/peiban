from typing import Any, Optional

from evals.completion_fns.openai import OpenAIChatCompletionFn


class SiliconflowOpenAIChatCompletionFn(OpenAIChatCompletionFn):
    def __init__(self, registry: Optional[Any] = None, **kwargs: Any):
        super().__init__(**kwargs)

