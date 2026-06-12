"""Core QA Agent Orchestrator.

This module coordinates the browser automation and LLM client to execute
autonomous test scripts using natural language instructions.
"""

import datetime
import logging
import os
from collections.abc import Callable
from typing import Any, Literal

from src.core.exceptions import ActionExecutionError, AgentError, LLMResponseParseError
from src.core.models import ActionIntent, ElementNode, StepReport, TestReport
from src.infrastructure.browser_service import BrowserService
from src.infrastructure.llm_client import LLMClient

logger = logging.getLogger(__name__)


class QABrowserAgent:
    """Orchestrates the Perceive-Act-Verify loop to test web pages using an LLM."""

    def __init__(self, browser_service: BrowserService, llm_client: LLMClient) -> None:
        """Initializes the orchestrator.

        Args:
            browser_service: The browser controller instance.
            llm_client: The LiteLLM client wrapper.
        """
        self.browser_service = browser_service
        self.llm_client = llm_client

    def _get_history_text(self, action: ActionIntent, node: ElementNode | None) -> str:
        """Generates a clean human-readable text description of an action."""
        act_type = action.action_type
        el_info = f"<{node.tag}> '{node.text}'" if node else f"ID: {action.element_id}"

        if act_type == "click":
            return f"Clicked element {el_info}"
        elif act_type == "type":
            return f"Typed '{action.value}' into element {el_info}"
        elif act_type == "select":
            return f"Selected option '{action.value}' in element {el_info}"
        elif act_type == "scroll":
            return f"Scrolled page {action.value}"
        elif act_type == "wait":
            return "Waited for page stability"
        elif act_type == "done":
            return "Completed task successfully"
        elif act_type == "fail":
            return f"Failed task: {action.reasoning}"
        return f"Executed action: {act_type}"

    async def _execute_action(
        self, action_intent: ActionIntent, target_node: ElementNode | None
    ) -> None:
        """Executes the mapped browser action using BrowserService."""
        act_type = action_intent.action_type
        if act_type == "click":
            assert target_node is not None
            await self.browser_service.click(target_node.selector)
        elif act_type == "type":
            assert target_node is not None
            val = action_intent.value or ""
            await self.browser_service.type(target_node.selector, val)
        elif act_type == "select":
            assert target_node is not None
            val = action_intent.value or ""
            await self.browser_service.select(target_node.selector, val)
        elif act_type == "scroll":
            direction: Literal["up", "down"] = "down"
            if action_intent.value == "up":
                direction = "up"
            await self.browser_service.scroll(direction)
        elif act_type == "wait":
            await self.browser_service.wait_for_stability(2000)

    def _save_report(
        self,
        target_url: str,
        task_description: str,
        step_reports: list[StepReport],
        final_status: Literal["success", "failure", "timeout"],
        final_error: str | None,
        trace_path: str | None,
        report_json_path: str,
        notify: Callable[[str, dict[str, Any]], Any],
    ) -> TestReport:
        """Compiles the final TestReport, writes it to disk, and notifies the UI."""
        report = TestReport(
            target_url=target_url,
            task_description=task_description,
            steps=step_reports,
            status=final_status,
            error_message=final_error,
            trace_path=trace_path,
        )

        try:
            with open(report_json_path, "w", encoding="utf-8") as f:
                f.write(report.model_dump_json(indent=2))
            notify(
                "log",
                {
                    "message": f"Test report written to {report_json_path}",
                    "level": "success",
                },
            )
        except Exception as e:
            logger.error("Failed to write test report JSON: %s", e)

        state_label = (
            "Finished (Success)"
            if final_status == "success"
            else f"Finished ({final_status.capitalize()})"
        )
        notify("status", {"state": state_label, "trace_path": trace_path or "N/A"})
        return report

    async def _setup_run(
        self,
        target_url: str,
        task_description: str,
        reports_dir: str,
        notify: Callable[[str, dict[str, Any]], Any],
    ) -> tuple[str, str | None, str, str]:
        """Sets up directories, starts browser/tracing, and navigates to target."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_folder = os.path.abspath(os.path.join(reports_dir, f"run_{timestamp}"))
        os.makedirs(run_folder, exist_ok=True)

        trace_path = os.path.join(run_folder, "trace.zip")
        report_json_path = os.path.join(run_folder, "report.json")

        if not self.browser_service.page:
            notify("status", {"state": "Starting Browser..."})
            await self.browser_service.start()

        await self.browser_service.start_tracing()

        notify("status", {"state": "Navigating to URL..."})
        notify("log", {"message": f"Navigating to {target_url}", "level": "info"})
        current_url = await self.browser_service.navigate(target_url)
        notify("status", {"url": current_url})

        return run_folder, trace_path, report_json_path, current_url

    async def _process_step(
        self,
        current_step: int,
        max_steps: int,
        run_folder: str,
        current_url: str,
        task_description: str,
        action_history_descriptions: list[str],
        notify: Callable[[str, dict[str, Any]], Any],
        credentials: dict[str, str] | None = None,
    ) -> tuple[ActionIntent, ElementNode | None, str, list[ElementNode]]:
        """Handles perception, screenshot, and consulting the LLM for the step."""
        notify(
            "status",
            {
                "state": f"Step {current_step}: Perceiving page DOM...",
                "step": current_step,
                "max_steps": max_steps,
            },
        )

        # Perceive: Extract visible interactive elements
        elements = await self.browser_service.prune_dom()

        # Take screenshot
        screenshot_filename = f"step_{current_step}.png"
        screenshot_path = os.path.join(run_folder, screenshot_filename)
        await self.browser_service.capture_screenshot(screenshot_path)
        notify("screenshot", {"path": screenshot_path})

        # Call LLM to determine next action
        notify("status", {"state": f"Step {current_step}: Consulting LLM..."})
        try:
            action_intent = await self.llm_client.get_next_action(
                task_description=task_description,
                current_url=current_url,
                elements=elements,
                history=action_history_descriptions,
                credentials=credentials,
            )
        except LLMResponseParseError as parse_err:
            error_msg = f"LLM responded with invalid JSON format: {parse_err}"
            notify("log", {"message": error_msg, "level": "error"})
            raise AgentError(error_msg) from parse_err

        notify(
            "log",
            {
                "message": f"LLM Reasoning (Step {current_step}): {action_intent.reasoning}",
                "level": "thought",
            },
        )

        # Map element_id to Playwright Selector
        target_node: ElementNode | None = None
        if action_intent.element_id:
            for el in elements:
                if el.id == action_intent.element_id:
                    target_node = el
                    break

            if not target_node and action_intent.action_type in (
                "click",
                "type",
                "select",
            ):
                err_msg = f"LLM requested action on non-existent element: {action_intent.element_id}"
                notify("log", {"message": err_msg, "level": "error"})
                raise ActionExecutionError(err_msg)

        return action_intent, target_node, screenshot_path, elements

    async def _execute_single_step(
        self,
        current_step: int,
        max_steps: int,
        run_folder: str,
        current_url: str,
        task_description: str,
        action_history_descriptions: list[str],
        step_reports: list[StepReport],
        notify: Callable[[str, dict[str, Any]], Any],
        credentials: dict[str, str] | None = None,
    ) -> tuple[str, Literal["success", "failure", "continue"], str | None]:
        """Executes a single step in the perceive-act-verify loop."""
        (
            action_intent,
            target_node,
            screenshot_path,
            elements,
        ) = await self._process_step(
            current_step=current_step,
            max_steps=max_steps,
            run_folder=run_folder,
            current_url=current_url,
            task_description=task_description,
            action_history_descriptions=action_history_descriptions,
            notify=notify,
            credentials=credentials,
        )

        action_text = self._get_history_text(action_intent, target_node)
        action_history_descriptions.append(action_text)
        notify(
            "log",
            {
                "message": f"Step {current_step} Action: {action_text}",
                "level": "action",
            },
        )

        if action_intent.action_type == "done":
            step_reports.append(
                StepReport(
                    step_number=current_step,
                    screenshot_path=screenshot_path,
                    dom_snapshot=elements,
                    action=action_intent,
                    success=True,
                )
            )
            return current_url, "success", None

        if action_intent.action_type == "fail":
            step_reports.append(
                StepReport(
                    step_number=current_step,
                    screenshot_path=screenshot_path,
                    dom_snapshot=elements,
                    action=action_intent,
                    success=False,
                    error_message=action_intent.reasoning,
                )
            )
            return current_url, "failure", action_intent.reasoning

        notify("status", {"state": f"Step {current_step}: Executing Action..."})
        step_success = True
        step_error = None
        try:
            await self._execute_action(action_intent, target_node)
        except Exception as action_err:
            step_success = False
            step_error = str(action_err)
            notify(
                "log",
                {"message": f"Action execution failed: {step_error}", "level": "error"},
            )
            raise ActionExecutionError(step_error) from action_err

        step_reports.append(
            StepReport(
                step_number=current_step,
                screenshot_path=screenshot_path,
                dom_snapshot=elements,
                action=action_intent,
                success=step_success,
                error_message=step_error,
            )
        )

        assert self.browser_service.page is not None
        new_url = self.browser_service.page.url
        notify("status", {"url": new_url})
        return new_url, "continue", None

    async def _cleanup_run(
        self, trace_path: str | None, notify: Callable[[str, dict[str, Any]], Any]
    ) -> str | None:
        """Stops Playwright tracing, saves the trace archive, and closes the browser."""
        notify("status", {"state": "Saving Playwright Trace..."})
        saved_trace_path = trace_path
        try:
            if trace_path is not None:
                await self.browser_service.stop_tracing(trace_path)
        except Exception as e:
            logger.error("Failed to stop and save Playwright trace: %s", e)
            saved_trace_path = None

        notify("status", {"state": "Stopping Browser..."})
        await self.browser_service.stop()
        return saved_trace_path

    async def run_task(
        self,
        target_url: str,
        task_description: str,
        max_steps: int = 15,
        reports_dir: str = "test_reports",
        credentials: dict[str, str] | None = None,
        update_callback: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> TestReport:
        """Runs the autonomous QA loop to achieve the specified task goal.

        Args:
            target_url: Starting URL of the test app.
            task_description: Description of the goal to achieve.
            max_steps: Maximum step limit before timeout.
            reports_dir: Directory where reports/traces/screenshots are saved.
            credentials: Optional key-value credentials dictionary.
            update_callback: Hook to notify TUI or console log of changes.

        Returns:
            The compiled TestReport metadata.
        """

        def notify(event_type: str, data: dict[str, Any]) -> None:
            if update_callback:
                try:
                    update_callback(event_type, data)
                except Exception as e:
                    logger.warning("Callback execution failed: %s", e)

        run_folder, trace_path, report_json_path, current_url = await self._setup_run(
            target_url=target_url,
            task_description=task_description,
            reports_dir=reports_dir,
            notify=notify,
        )

        step_reports: list[StepReport] = []
        action_history_descriptions: list[str] = []
        current_step = 1
        final_status: Literal["success", "failure", "timeout"] = "timeout"
        final_error: str | None = None

        try:
            while current_step <= max_steps:
                (
                    current_url,
                    step_result,
                    step_error_msg,
                ) = await self._execute_single_step(
                    current_step=current_step,
                    max_steps=max_steps,
                    run_folder=run_folder,
                    current_url=current_url,
                    task_description=task_description,
                    action_history_descriptions=action_history_descriptions,
                    step_reports=step_reports,
                    notify=notify,
                    credentials=credentials,
                )

                if step_result == "success":
                    final_status = "success"
                    break
                elif step_result == "failure":
                    final_status = "failure"
                    final_error = step_error_msg
                    break

                current_step += 1

            if current_step > max_steps and final_status == "timeout":
                final_error = f"Exceeded maximum allowed steps ({max_steps})."
                notify("log", {"message": final_error, "level": "error"})

        except Exception as e:
            final_status = "failure"
            final_error = str(e)
            logger.exception("Agent run loop encountered critical error")
            notify(
                "log",
                {"message": f"Critical run error: {final_error}", "level": "error"},
            )
        finally:
            trace_path = await self._cleanup_run(trace_path, notify)

        # Compile and write report
        report = self._save_report(
            target_url=target_url,
            task_description=task_description,
            step_reports=step_reports,
            final_status=final_status,
            final_error=final_error,
            trace_path=trace_path,
            report_json_path=report_json_path,
            notify=notify,
        )
        return report
