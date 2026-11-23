"""Chromium réel : formulaire, fichier, job, clavier, mobile et axe."""

import base64
import hashlib
import ipaddress
import json
import os
import time
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

out = Path("/evidence")
errors = []
png = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
)
with sync_playwright() as p:
    node = os.getenv("BC3_NODE_IP")
    args = (
        []
        if not node
        else ["--host-resolver-rules=MAP bc3.local " + str(ipaddress.ip_address(node))]
    )
    browser = p.chromium.launch(args=args)
    ctx = browser.new_context(
        ignore_https_errors=True,
        viewport={"width": 1440, "height": 1000},
        accept_downloads=True,
    )
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(os.getenv("BC3_BROWSER_URL", "https://front:8443/"), wait_until="networkidle")
    page.keyboard.press("Tab")
    expect(page.get_by_role("link", name="Aller au contenu")).to_be_focused()
    page.keyboard.press("Enter")
    page.get_by_label("Identifiant", exact=True).fill("thomas")
    page.get_by_label("Mot de passe", exact=True).fill(
        Path("/run/secrets/demo_password").read_text().strip()
    )
    page.get_by_role("button", name="Se connecter", exact=True).click()
    expect(page.get_by_role("heading", name="Vos tickets, au même endroit.")).to_be_visible()
    page.get_by_role("button", name="Nouveau ticket", exact=True).click()
    title = "Fixture navigateur " + uuid.uuid4().hex[:8]
    page.get_by_label("Objet", exact=True).fill(title)
    page.get_by_label("Description", exact=True).fill(
        "Synthetic browser test, not a real customer. My card has not arrived after two weeks."
    )
    page.get_by_role("button", name="Créer le ticket", exact=True).click()
    expect(page.locator(".detail h2")).to_have_text(title)
    page.get_by_label("Ajouter une pièce jointe", exact=True).set_input_files(
        {"name": "fixture.png", "mimeType": "image/png", "buffer": png}
    )
    page.get_by_role("button", name="Ajouter le fichier", exact=True).click()
    expect(page.locator(".attachments")).to_contain_text("PNG")
    with page.expect_download() as download:
        page.get_by_role("button", name="Télécharger le PNG", exact=False).click()
    assert Path(download.value.path()).read_bytes() == png
    page.get_by_role("button", name="Prendre en charge", exact=True).click()
    expect(page.locator(".detail .badge")).to_have_text("En cours")
    started = time.monotonic()
    with page.expect_response(lambda r: r.url.endswith("/intent"), timeout=60000) as prediction:
        page.get_by_role("button", name="Suggérer une catégorie", exact=True).click()
    response = prediction.value
    assert response.status == 200, response.text()
    inference_seconds = time.monotonic() - started
    expect(page.locator(".detail")).to_contain_text("Version banking77-c1-0", timeout=10000)
    expect(page.locator(".detail ol li")).to_have_count(3)
    assert 1 <= page.locator(".ticket-list > li").count() <= 10
    page.get_by_label("Rechercher dans les tickets chargés", exact=True).fill(title)
    expect(page.locator(".ticket-list > li")).to_have_count(1)
    page.evaluate(Path("/opt/axe.min.js").read_text())
    axe = page.evaluate(
        "async()=>await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}})"
    )
    page.screenshot(path=str(out / "tickets-desktop.png"), full_page=True)
    page.get_by_role("button", name="Exports asynchrones", exact=True).click()
    page.get_by_role("button", name="Préparer un export", exact=True).click()
    expect(page.locator(".messages")).to_contain_text("Demande enregistrée")
    expect(page.locator("tbody tr").first.locator(".badge")).to_have_text("Prêt", timeout=40000)
    with page.expect_download() as download:
        page.locator("tbody tr").first.get_by_role("button", name="Télécharger le CSV").click()
    assert title in Path(download.value.path()).read_text(encoding="utf-8-sig")
    page.screenshot(path=str(out / "exports-desktop.png"), full_page=True)
    mobile = ctx.new_page()
    mobile.set_viewport_size({"width": 390, "height": 844})
    mobile.goto(os.getenv("BC3_BROWSER_URL", "https://front:8443/"), wait_until="networkidle")
    expect(mobile.get_by_role("heading", name="Vos tickets, au même endroit.")).to_be_visible()
    mobile.get_by_label("Rechercher dans les tickets chargés", exact=True).fill(title)
    expect(mobile.locator(".ticket-list > li")).to_have_count(1)
    mobile.screenshot(path=str(out / "tickets-mobile.png"), full_page=True)
    overflow = mobile.evaluate("document.documentElement.scrollWidth>innerWidth+1")
    report = {
        "event": "real_browser",
        "ticket_creation": True,
        "actual_intent_suggestion_visible": True,
        "inference_observed_seconds": inference_seconds,
        "private_upload_download_exact": True,
        "async_export_download_contains_fixture": True,
        "keyboard_skip": True,
        "mobile_global_overflow": overflow,
        "javascript_errors": errors,
        "axe_violations": [
            {
                "id": v["id"],
                "impact": v["impact"],
                "nodes": [n["target"] for n in v["nodes"]],
            }
            for v in axe["violations"]
        ],
        "axe_incomplete": len(axe["incomplete"]),
        "tls_scope": "Self-signed browser demo context ignores trust only; separate HTTPX tests verify CA and reject untrusted TLS",
        "screenshots": {
            f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in out.glob("*.png")
        },
    }
    (out / "checks.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    browser.close()
    assert not errors and not overflow and not axe["violations"]
