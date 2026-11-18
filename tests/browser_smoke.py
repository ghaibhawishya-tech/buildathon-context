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
        editor = page.get_by_label("Untrusted source note")
        editor.fill("Temporary note")
        page.get_by_role("button", name="Clear note").click()
        expect(editor).to_have_value("")
        editor.fill(note)
        page.get_by_label("Rehearse an out-of-scope proposal").select_option("send_message")
        page.get_by_role("button", name="Run experiment").click()
        expect(page.get_by_text("Legitimate task completed", exact=False)).to_be_visible()
        expect(page.get_by_text("DENY · send_message · not executed")).to_be_visible()
        expect(page.get_by_text("ALLOW · read_source · executed")).to_be_visible()
        expect(page.locator("#original")).to_have_text(note)
        expect(page.locator("#scoped")).to_contain_text("derived_structured_data")
        expect(page.locator("#scoped")).not_to_contain_text(note)
        page.get_by_text("Full run evidence").click()
        expect(page.locator("#payload")).to_contain_text(note)

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
        proposal = page.get_by_label("Proposal JSON")
        custom = json.dumps({"tool": "read_source", "arguments": {"resource": "project-update"}})
        proposal.fill(custom)
        held = []
        page.route("**/gateway/authorize-action", lambda route: held.append(route))
        with page.expect_request("**/gateway/authorize-action"):
            page.get_by_role("button", name="Check authorization").click()
        page.get_by_label("Scenario", exact=True).select_option("shopping")
        expect(proposal).to_have_value(custom)
        with page.expect_response("**/gateway/authorize-action"):
            held[0].fulfill(json={"decision": "ALLOW", "rule": "previous_scope"})
        expect(page.locator("#decision")).to_be_empty()
        page.get_by_role("button", name="Use example proposal").click()
        expect(proposal).to_have_value(json.dumps({
            "tool": "read_source", "arguments": {"resource": "price-catalog"},
        }, indent=2))
        page.get_by_role("button", name="Workspace review", exact=False).first.click()
        expect(page.locator("#outcome")).to_contain_text("Workspace review")

        other = browser.new_page()
        other.route("**/metrics", lambda route: route.fulfill(status=503, json={"detail": "Unavailable."}))
        other.goto(url)
        expect(other.locator("#history-status")).to_contain_text("Could not load history")
        expect(other.locator("#health")).to_contain_text("FIXTURE MODE AVAILABLE")
        other.get_by_role("button", name="Run experiment").click()
        expect(other.locator("#status")).to_have_text("Run recorded.")
        browser.close()


if __name__ == "__main__":
    check_lab(sys.argv[1])
