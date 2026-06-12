import asyncio
from src.tui.app import PitaApp
from src.tui.screens.project_form import ProjectFormScreen
from textual.widgets import Input, OptionList

async def main():
    app = PitaApp()
    async with app.run_test() as pilot:
        # Click the new project button to show the modal form
        await pilot.click("#btn_new_project")
        await asyncio.sleep(0.5)
        
        screen = app.screen
        if not isinstance(screen, ProjectFormScreen):
            print("Failed: active screen is not ProjectFormScreen")
            return
            
        screen.query_one("#proj_name", Input).value = "TestProj"
        screen.query_one("#proj_url", Input).value = "https://example.com"
        
        # Fill in the test case details
        screen.query_one("#new_test_name", Input).value = "My TestCase"
        screen.query_one("#new_test_desc", Input).value = "A test case description"
        
        # Click the "Add Test Case" button
        await pilot.click("#btn_add_test")
        await asyncio.sleep(0.5)
        
        print(f"Tests list size: {len(screen.tests)}")
        tests_list = screen.query_one("#proj_tests_list", OptionList)
        print(f"OptionList count: {tests_list.option_count}")
        
        # Click save
        await pilot.click("#btn_save")
        await asyncio.sleep(0.5)
        print("Save clicked successfully")

if __name__ == "__main__":
    asyncio.run(main())
