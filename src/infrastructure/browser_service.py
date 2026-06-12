"""Playwright browser automation service.

This module implements the browser lifecycle, tracing, screenshots, and
the HTML DOM pruning algorithm to reduce tree size for LLM ingestion.
"""

import logging
from typing import Literal

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from src.core.exceptions import (
    ActionExecutionError,
    BrowserServiceError,
    NavigationError,
)
from src.core.models import ElementNode

logger = logging.getLogger(__name__)

# JavaScript snippet executed in-browser to identify, tag, and extract visible interactive elements.
DOM_PRUNE_JS = """
() => {
    const interactiveSelector = 'a, button, input, select, textarea, [onclick], [role="button"], [role="link"], [role="checkbox"], [role="menuitem"], [role="tab"], [contenteditable="true"]';
    const elements = document.querySelectorAll(interactiveSelector);
    const result = [];
    let index = 1;

    for (const el of elements) {
        // Basic visibility checks
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        if (
            rect.width === 0 ||
            rect.height === 0 ||
            style.display === 'none' ||
            style.visibility === 'hidden' ||
            style.opacity === '0'
        ) {
            continue;
        }

        // Find existing unique identifier or generate a temporary data-qa-id
        let qaId = el.getAttribute('data-qa-id');
        if (!qaId) {
            qaId = el.getAttribute('data-testid');
        }
        if (!qaId) {
            qaId = el.getAttribute('id');
        }
        if (!qaId) {
            do {
                qaId = `qa-${index++}`;
            } while (document.querySelector(`[data-qa-id="${qaId}"], [id="${qaId}"], [data-testid="${qaId}"]`));
            el.setAttribute('data-qa-id', qaId);
        }

        // Capture important HTML attributes
        const attrs = {};
        for (const attr of el.attributes) {
            if (['id', 'name', 'type', 'placeholder', 'role', 'value', 'class', 'href'].includes(attr.name)) {
                attrs[attr.name] = attr.value;
            }
        }

        // Extract and clean inner text content
        let text = (el.innerText || el.textContent || '').trim();
        if (el.tagName === 'INPUT' && (el.type === 'button' || el.type === 'submit')) {
            text = el.value || '';
        }
        if (text.length > 100) {
            text = text.substring(0, 97) + '...';
        }

        // Generate a reliable, specific Playwright selector
        let selector = el.tagName.toLowerCase();
        if (el.id) {
            selector = `#${el.id}`;
        } else if (el.name) {
            selector = `${el.tagName.toLowerCase()}[name="${el.name}"]`;
        } else {
            selector = `[data-qa-id="${qaId}"]`;
        }

        result.push({
            id: qaId,
            tag: el.tagName.toLowerCase(),
            text: text,
            attributes: attrs,
            selector: selector
        });
    }
    return result;
}
"""


class BrowserService:
    """Manages the Playwright browser session, user actions, and DOM extraction."""

    def __init__(
        self, headless: bool = True, ignore_https_errors: bool = False
    ) -> None:
        """Initializes the browser service.

        Args:
            headless: Whether to run the browser in headless mode.
            ignore_https_errors: Whether to ignore HTTPS/SSL certificate errors.
        """
        self.headless = headless
        self.ignore_https_errors = ignore_https_errors
        self._playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def start(self) -> None:
        """Starts the Playwright instance and launches Chromium."""
        try:
            self._playwright = await async_playwright().start()
            self.browser = await self._playwright.chromium.launch(
                headless=self.headless
            )
            # Create a context with a standard desktop viewport size
            self.context = await self.browser.new_context(
                viewport={"width": 1280, "height": 800},
                ignore_https_errors=self.ignore_https_errors,
            )
            self.page = await self.context.new_page()
            logger.info("Browser session successfully started.")
        except Exception as e:
            raise BrowserServiceError(f"Failed to start browser service: {e}") from e

    async def stop(self) -> None:
        """Closes all pages, contexts, and terminates Playwright."""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self._playwright:
                await self._playwright.stop()
            logger.info("Browser session stopped.")
        except Exception as e:
            logger.error("Error encountered while stopping browser service: %s", e)
        finally:
            self.page = None
            self.context = None
            self.browser = None
            self._playwright = None

    async def navigate(self, url: str) -> str:
        """Navigates to the specified URL and waits for stability.

        Args:
            url: The destination web page address.

        Returns:
            The final URL after redirects.
        """
        if not self.page:
            raise BrowserServiceError("Browser is not started. Call start() first.")

        try:
            logger.info("Navigating to: %s", url)
            await self.page.goto(url)
            await self.wait_for_stability()
            return self.page.url
        except Exception as e:
            raise NavigationError(f"Failed to navigate to {url}: {e}") from e

    async def wait_for_stability(self, timeout_ms: int = 1500) -> None:
        """Waits for network to settle and allow dynamic Vue.js/HTMX UI swap rendering.

        Args:
            timeout_ms: Safety buffer to sleep after network idle state.
        """
        if not self.page:
            return

        try:
            # Wait for network requests to settle
            await self.page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            logger.warning("Network idle state not reached within timeout.")

        try:
            # Additional small stability check for HTMX/Vue swaps
            await self.page.wait_for_timeout(timeout_ms)
        except Exception as e:
            logger.warning("Error during stability wait: %s", e)

    async def prune_dom(self) -> list[ElementNode]:
        """Runs the DOM pruning script inside the page.

        Returns:
            A list of pruned ElementNodes representing interactive elements.
        """
        if not self.page:
            raise BrowserServiceError("Page is not initialized.")

        try:
            raw_nodes = await self.page.evaluate(DOM_PRUNE_JS)
            return [ElementNode(**node) for node in raw_nodes]
        except Exception as e:
            raise BrowserServiceError(f"Failed to prune DOM: {e}") from e

    async def capture_screenshot(self, filepath: str) -> None:
        """Captures a screenshot of the current page viewport.

        Args:
            filepath: Destination path to save the screenshot.
        """
        if not self.page:
            raise BrowserServiceError("Page is not initialized.")

        try:
            await self.page.screenshot(path=filepath)
            logger.info("Screenshot saved to %s", filepath)
        except Exception as e:
            raise BrowserServiceError(f"Failed to capture screenshot: {e}") from e

    async def start_tracing(self) -> None:
        """Starts Playwright trace recording."""
        if not self.context:
            raise BrowserServiceError("Context is not initialized.")

        try:
            await self.context.tracing.start(
                screenshots=True, snapshots=True, sources=True
            )
            logger.info("Playwright tracing started.")
        except Exception as e:
            raise BrowserServiceError(f"Failed to start tracing: {e}") from e

    async def stop_tracing(self, filepath: str) -> None:
        """Stops trace recording and saves the zip archive.

        Args:
            filepath: Destination path for the trace zip archive.
        """
        if not self.context:
            raise BrowserServiceError("Context is not initialized.")

        try:
            await self.context.tracing.stop(path=filepath)
            logger.info("Playwright trace saved to %s", filepath)
        except Exception as e:
            raise BrowserServiceError(f"Failed to stop tracing: {e}") from e

    async def click(self, selector: str) -> None:
        """Clicks on the element identified by the selector.

        Args:
            selector: CSS or XPath selector of target element.
        """
        if not self.page:
            raise BrowserServiceError("Page is not initialized.")

        try:
            await self.page.click(selector, timeout=5000)
            await self.wait_for_stability()
        except Exception as e:
            raise ActionExecutionError(
                f"Click action failed on selector {selector}: {e}"
            ) from e

    async def type(self, selector: str, text: str) -> None:
        """Fills input text into the target element.

        Args:
            selector: CSS selector for input/textarea.
            text: Value to input.
        """
        if not self.page:
            raise BrowserServiceError("Page is not initialized.")

        try:
            # Focus, clear existing text, then type
            await self.page.focus(selector, timeout=5000)
            await self.page.fill(selector, "")
            await self.page.type(selector, text)
            await self.wait_for_stability()
        except Exception as e:
            raise ActionExecutionError(
                f"Type action failed on selector {selector}: {e}"
            ) from e

    async def select(self, selector: str, value: str) -> None:
        """Selects an option in a select dropdown by value or label.

        Args:
            selector: CSS selector for the select element.
            value: Option value or text to choose.
        """
        if not self.page:
            raise BrowserServiceError("Page is not initialized.")

        try:
            await self.page.select_option(selector, value=value, timeout=5000)
            await self.wait_for_stability()
        except Exception as e:
            raise ActionExecutionError(
                f"Select action failed on selector {selector} for value {value}: {e}"
            ) from e

    async def scroll(self, direction: Literal["up", "down"]) -> None:
        """Scrolls the viewport page up or down.

        Args:
            direction: Direction to scroll.
        """
        if not self.page:
            raise BrowserServiceError("Page is not initialized.")

        try:
            scroll_amount = (
                "window.innerHeight" if direction == "down" else "-window.innerHeight"
            )
            await self.page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            await self.wait_for_stability()
        except Exception as e:
            raise ActionExecutionError(
                f"Scroll action failed to move {direction}: {e}"
            ) from e
