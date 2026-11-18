"""Run against a local lab: python tests/browser_smoke.py http://127.0.0.1:8000."""
import json
import sys

from playwright.sync_api import expect, sync_playwright


def check_lab(url):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chromium")
        page = browser.new_page(accept_downloads=True, viewport={"width": 1280, "height": 900})
        page.goto(url)
        page.get_by_label("Scenario", exact=True).select_option("workspace")
        note = "<b>Fictional memo</b>"
        page.get_by_label("Untrusted source note").fill(note)
        page.get_by_label("Rehearse an out-of-scope proposal").select_option("send_message")
        page.get_by_role("button", name="Run experiment").click()
        expect(page.get_by_text("Legitimate task completed", exact=False)).to_be_visible()
        expect(page.get_by_text("DENY · send_message · not executed")).to_be_visible()
        expect(page.get_by_text("ALLOW · read_source · executed")).to_be_visible()
        page.get_by_text("Full run evidence").click()
        expect(page.get_by_text(note, exact=False)).to_be_visible()

        with page.expect_download() as download:
            page.get_by_role("button", name="Export JSON").click()
        snapshot = json.loads(download.value.path().read_text())
        assert snapshot["source"]["content"] == note
        assert snapshot["events"][0]["side_effect"] is False

        page.get_by_role("button", name="Check authorization").click()
        expect(page.locator("#decision")).to_contain_text("scoped_fixture_read")
        expect(page.get_by_role("button", name="Workspace review", exact=False).first).to_be_visible()
        page.set_viewport_size({"width": 390, "height": 840})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        browser.close()


if __name__ == "__main__":
    check_lab(sys.argv[1])
