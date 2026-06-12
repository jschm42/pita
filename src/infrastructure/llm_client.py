"""LiteLLM integration client.

This module formats prompts, calls the LLM asynchronously, and parses
the structured action intent JSON responses.
"""

import json
import logging
import re
from typing import Any

import litellm

from src.core.exceptions import LLMClientError, LLMResponseParseError
from src.core.models import ActionIntent, ElementNode

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an autonomous web testing assistant. Your goal is to help a user test their web application by achieving a specified goal.
You will receive:
1. The target task description.
2. The current page URL.
3. A list of interactive, visible elements present in the DOM.
4. The history of actions executed in this session so far.

You must decide on the NEXT single action to execute.
Choose from the following action types:
- click: Click on an element. Requires target element_id.
- type: Enter text into an input or textarea. Requires target element_id and value.
- select: Select an option in a select element. Requires target element_id and value.
- scroll: Scroll the page viewport. Requires value ("up" or "down").
- wait: Wait for stability, animations, or network idle.
- done: Mark the test run as successfully completed when the target goal has been fully achieved.
- fail: Mark the test run as failed if the goal is impossible to achieve or an error is encountered.

You MUST respond strictly with a JSON object containing the following structure:
{
    "reasoning": "A step-by-step thinking process explaining what you see, what needs to be done, and why you choose this specific action.",
    "action_type": "click" | "type" | "select" | "scroll" | "wait" | "done" | "fail",
    "element_id": "qa-X" (or null/absent if not applicable),
    "value": "text to type / option value / scroll direction" (or null/absent if not applicable)
}

Think carefully before choosing. Output ONLY the JSON block. Do not include any other conversational filler text.
"""


class LLMClient:
    """Client for interacting with LLM models using LiteLLM."""

    def __init__(
        self, model: str = "ollama/llama3", api_base: str | None = None
    ) -> None:
        """Initializes the LLM Client.

        Args:
            model: LiteLLM model identifier (e.g., 'ollama/llama3', 'openai/gpt-4o').
            api_base: Base URL endpoint for LLM API (e.g., local Ollama instance).
        """
        self.model = model
        self.api_base = api_base

    def _format_elements_list(self, elements: list[ElementNode]) -> str:
        """Formats the list of elements into a clean, text-based representation."""
        if not elements:
            return "No visible interactive elements found on this page."

        lines = []
        for el in elements:
            attrs_str = ", ".join(f'{k}="{v}"' for k, v in el.attributes.items())
            lines.append(
                f"- ID: {el.id} | Tag: <{el.tag}> | Text: '{el.text}' | Attributes: [{attrs_str}]"
            )
        return "\n".join(lines)

    def _format_history_list(self, history: list[str]) -> str:
        """Formats the history of steps into a numbered list."""
        if not history:
            return "No actions executed yet (First Step)."

        return "\n".join(f"{i + 1}. {step}" for i, step in enumerate(history))

    def _clean_and_parse_json(self, text: str) -> dict[str, Any]:
        """Extracts and parses JSON from the LLM response text.

        Uses regex to search for markdown json blocks or raw braces.
        """
        text = text.strip()

        # Try searching for a markdown json code block
        json_block_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if json_block_match:
            candidate = json_block_match.group(1).strip()
            try:
                return json.loads(candidate)  # type: ignore[no-any-return]
            except json.JSONDecodeError:
                pass

        # Try searching for a standard markdown code block
        code_block_match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
        if code_block_match:
            candidate = code_block_match.group(1).strip()
            try:
                return json.loads(candidate)  # type: ignore[no-any-return]
            except json.JSONDecodeError:
                pass

        # Try to find standard JSON boundaries { ... }
        brace_match = re.search(r"(\{.*\})", text, re.DOTALL)
        if brace_match:
            candidate = brace_match.group(1).strip()
            try:
                return json.loads(candidate)  # type: ignore[no-any-return]
            except json.JSONDecodeError:
                pass

        # Fallback to direct json.loads
        try:
            return json.loads(text)  # type: ignore[no-any-return]
        except json.JSONDecodeError as e:
            raise LLMResponseParseError(
                f"Failed to parse JSON from LLM output. Raw output: '{text}'"
            ) from e

    def _format_credentials(self, credentials: dict[str, str] | None) -> str:
        """Formats credentials mapping into a text summary for LLM prompt."""
        if not credentials:
            return "No preconfigured credentials available for this run."

        lines = []
        for key, value in credentials.items():
            lines.append(f"- {key}: '{value}'")
        return "\n".join(lines)

    async def get_next_action(
        self,
        task_description: str,
        current_url: str,
        elements: list[ElementNode],
        history: list[str],
        credentials: dict[str, str] | None = None,
    ) -> ActionIntent:
        """Queries the LLM for the next action to perform.

        Args:
            task_description: The final goal of the test.
            current_url: The current URL of the page being tested.
            elements: List of visible interactive element nodes.
            history: Human-readable logs of steps executed so far.
            credentials: Key-value credentials dictionary.

        Returns:
            The parsed ActionIntent object.
        """
        formatted_elements = self._format_elements_list(elements)
        formatted_history = self._format_history_list(history)
        formatted_creds = self._format_credentials(credentials)

        user_prompt = (
            f"GOAL: {task_description}\n\n"
            f"CURRENT URL: {current_url}\n\n"
            f"AVAILABLE CREDENTIALS (use for inputs if required by form fields):\n"
            f"{formatted_creds}\n\n"
            f"VISIBLE INTERACTIVE ELEMENTS:\n"
            f"{formatted_elements}\n\n"
            f"HISTORY OF ACTIONS EXECUTION:\n"
            f"{formatted_history}\n\n"
            f"Decide the next single action to take. Return strictly valid JSON."
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            logger.info("Calling model '%s' via LiteLLM...", self.model)
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.1,  # Low temperature to keep outputs deterministic
            }
            if self.api_base:
                kwargs["api_base"] = self.api_base

            # Use asynchronous completion
            response = await litellm.acompletion(**kwargs)
            response_text = response.choices[0].message.content or ""
            logger.debug("Raw LLM response: %s", response_text)

            # Parse and validate with Pydantic
            parsed_json = self._clean_and_parse_json(response_text)
            action_intent = ActionIntent.model_validate(parsed_json)
            return action_intent

        except LLMResponseParseError as e:
            logger.error("JSON parsing error: %s", e)
            raise
        except Exception as e:
            logger.error("LLM completion call failed: %s", e)
            raise LLMClientError(f"LLM request failed: {e}") from e
