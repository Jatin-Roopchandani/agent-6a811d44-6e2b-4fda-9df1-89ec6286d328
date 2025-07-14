from typing import AsyncGenerator
from google.adk.agents import LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from pydantic import BaseModel

# You may need to import or define GEMINI_2_0_FLASH_STR here or pass it as a parameter

def structure_output(
    orig_output_key: str, output_schema: BaseModel, output_key: str, ctx: InvocationContext, model=None
) -> AsyncGenerator[Event, None]:
    """
    Structure raw output using a separate LLM call with schema validation.
    This prevents JSON validation errors by using a two-step process:
    1. First LLM generates raw output
    2. Second LLM structures it according to the schema
    """
    name = f"structure_output_{orig_output_key}_{output_key}"
    get_structured_output = LlmAgent(
        name=name,
        model=model,  # Model should be passed in or set as default
        instruction=f"""
            Output the following:
            <output_value>
            {{{{{orig_output_key}}}}}
            </output_value>
            """,
        output_key=output_key,
        output_schema=output_schema,
    )

    ctx.branch = name
    return get_structured_output.run_async(ctx) 