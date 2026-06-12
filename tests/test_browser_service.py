"""Integration tests for BrowserService using a local mock HTTP server."""

from collections.abc import Generator

import pytest

from src.infrastructure.browser_service import BrowserService
from tests.mock_server import MockServer


@pytest.fixture(scope="module")
def local_server() -> Generator[MockServer, None, None]:
    """Starts a local mock web server for the duration of the test module."""
    server = MockServer()
    server.start()
    yield server
    server.stop()


@pytest.mark.asyncio
async def test_browser_navigation_and_dom_prune(local_server: MockServer) -> None:
    """Verifies that BrowserService navigates, prunes DOM, types, and clicks successfully."""
    # Run browser in headless mode for speed
    service = BrowserService(headless=True)
    await service.start()

    try:
        # Navigate to local mock server login page
        url = await service.navigate(local_server.url)
        assert local_server.url in url

        # Prune DOM and check extracted element nodes
        elements = await service.prune_dom()

        # Verify we captured the inputs and button
        assert len(elements) >= 3

        username_node = None
        password_node = None
        submit_node = None

        for el in elements:
            if el.attributes.get("data-qa-id") == "username-input":
                username_node = el
            elif el.attributes.get("data-qa-id") == "password-input":
                password_node = el
            elif el.attributes.get("data-qa-id") == "login-btn":
                submit_node = el

        # If ids were not parsed in data-qa-id, check fallback to elements details
        if not username_node:
            username_node = next(
                (el for el in elements if el.id == "username-input"), None
            )
        if not password_node:
            password_node = next(
                (el for el in elements if el.id == "password-input"), None
            )
        if not submit_node:
            submit_node = next((el for el in elements if el.id == "login-btn"), None)

        assert username_node is not None
        assert password_node is not None
        assert submit_node is not None

        # Type correct credentials
        await service.type(username_node.selector, "tomsmith")
        await service.type(password_node.selector, "SuperSecretPassword!")

        # Click submit
        await service.click(submit_node.selector)

        # Check that we reached the secure area successfully
        assert service.page is not None
        content = await service.page.content()
        assert "Welcome to the secure area" in content

    finally:
        await service.stop()
