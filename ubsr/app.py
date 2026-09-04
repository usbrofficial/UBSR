"""Application entry point."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from ubsr import __version__  # noqa: E402
from ubsr.config import APP_ID, APP_NAME, APP_TAGLINE, DB_PATH, MEDIA_DIR, Settings, ensure_dirs  # noqa: E402
from ubsr.db import Database  # noqa: E402
from ubsr.personas import seed_database  # noqa: E402
from ubsr.simulation import World  # noqa: E402

log = logging.getLogger("ubsr")


class UBSRApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window = None
        self.db = None
        self.settings = None
        self.world = None
        GLib.set_application_name(APP_NAME)

    def do_startup(self):
        Adw.Application.do_startup(self)
        ensure_dirs()
        self.settings = Settings()
        self.db = Database(DB_PATH)
        seed_database(self.db, MEDIA_DIR)
        self.world = World(self.db, self.settings, MEDIA_DIR)
        self.world.start()

        css = Gtk.CssProvider()
        css.load_from_path(str(Path(__file__).parent / "ui" / "style.css"))
        from gi.repository import Gdk

        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        icon_dir = Path(__file__).parent / "data" / "icons"
        if icon_dir.is_dir():
            Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(str(icon_dir))

        for name, callback, accels in (
            ("preferences", self._on_preferences, ["<primary>comma"]),
            ("about", self._on_about, []),
            ("quit", lambda *_: self.quit(), ["<primary>q"]),
            ("new-post", lambda *_: self.window and self.window.compose(), ["<primary>n"]),
            ("open-chat", self._on_open_chat, []),
        ):
            action = Gio.SimpleAction.new(name, GLib.VariantType.new("i") if name == "open-chat" else None)
            action.connect("activate", callback)
            self.add_action(action)
            if accels:
                self.set_accels_for_action(f"app.{name}", accels)

    def do_activate(self):
        if self.window is None:
            from ubsr.ui.window import MainWindow

            self.window = MainWindow(self, self.db, self.settings, self.world)
        self.window.present()

    def do_shutdown(self):
        if self.world:
            self.world.stop()
        if self.db:
            self.db.close()
        Adw.Application.do_shutdown(self)

    # ------------------------------------------------------------------
    def _on_preferences(self, *_):
        if self.window:
            self.window.open_preferences()

    def _on_open_chat(self, _action, param):
        if self.window and param is not None:
            self.window.present()
            self.window.messages.open_conversation(param.get_int32())
            self.window.view_stack.set_visible_child_name("messages")

    def _on_about(self, *_):
        about = Gtk.AboutDialog(
            transient_for=self.window, modal=True, program_name=APP_NAME, version=__version__,
            comments=f"{APP_TAGLINE}\nA private photo network where everyone except you is AI.",
            logo_icon_name=APP_ID,
        )
        about.present()

    def notify_message(self, sender: str, text: str, conversation_id: int) -> None:
        note = Gio.Notification.new(sender)
        note.set_body(text[:200])
        note.set_default_action_and_target("app.open-chat", GLib.Variant("i", int(conversation_id)))
        self.send_notification(f"dm-{conversation_id}", note)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.DEBUG if os.environ.get("UBSR_DEBUG") else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    app = UBSRApplication()
    return app.run(argv if argv is not None else sys.argv)
