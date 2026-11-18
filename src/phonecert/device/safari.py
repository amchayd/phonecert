"""Open a page in Safari on the cabled phone, from the Mac."""
import asyncio


def open_in_safari(url: str, timeout: float = 10.0) -> dict:
    """Open `url` in ordinary Safari on the cabled phone. Returns {"ok": bool, "detail": str}.

    Uses Safari's Web Inspector (Settings → Apps → Safari → Advanced → Web Inspector): start Safari,
    attach to a tab, navigate it. Deliberately NOT `pymobiledevice3 webinspector launch`: that opens an
    automation window which closes when the command exits. The CLI has no non-interactive way to do
    this, so this one function uses the pymobiledevice3 Python API (11.50) — everything is inside the
    try, a library change can only turn it into {"ok": False}.
    """
    try:
        from pymobiledevice3.lockdown import create_using_usbmux
        from pymobiledevice3.services.webinspector import SAFARI, WebinspectorService

        async def go() -> dict:
            inspector = WebinspectorService(lockdown=await create_using_usbmux())
            await inspector.connect()
            try:
                async with inspector:
                    await inspector.open_app(SAFARI, timeout)
                    pages = []
                    for _ in range(5):   # the tab list arrives a moment after Safari comes to the front
                        pages = [x for x in await inspector.get_open_application_pages(timeout=1)
                                 if x.application.bundle == SAFARI]
                        if pages:
                            break
                    if not pages:
                        return {"ok": False, "detail": "Safari is open but shows no tab to use. Open any page in Safari on the phone and try again."}
                    session = await inspector.inspector_session(pages[0].application, pages[0].page)
                    await session.navigate_to_url(url)
                    return {"ok": True, "detail": "opened in Safari"}
            finally:
                await inspector.close()

        return asyncio.run(asyncio.wait_for(go(), timeout + 20))
    except Exception as e:  # noqa: BLE001 — best effort; the QR code always remains
        name, msg = type(e).__name__, str(e)
        if "NotEnabled" in name:
            return {"ok": False, "detail": "Web Inspector is off on the phone. Switch it on in Settings → Apps → Safari → Advanced → Web Inspector, then press the button again."}
        if "NoDevice" in name or "not connected" in msg.lower():
            return {"ok": False, "detail": "No phone on the cable. Connect it, unlock it, and press the button again."}
        return {"ok": False, "detail": f"{name}: {msg}".rstrip(": ") + ". Check that the phone is unlocked."}
