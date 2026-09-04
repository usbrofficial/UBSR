"""Preferences window."""

from __future__ import annotations

import threading

from gi.repository import Adw, GLib, Gtk

from mirage.ai import AIError, ChatMessage, make_backend
from mirage.ui.widgets import confirm, entry_row

BACKENDS = [("anthropic", "Claude (Anthropic API)"), ("openai_compat", "Local / OpenAI-compatible server")]
EFFORTS = ["low", "medium", "high"]
ACTIVITY = [("quiet", "Quiet"), ("normal", "Normal"), ("busy", "Busy")]


def _combo_row(title: str, options: list[tuple[str, str]], current: str, subtitle: str = "") -> Adw.ComboRow:
    row = Adw.ComboRow(title=title, subtitle=subtitle)
    model = Gtk.StringList()
    for _, name in options:
        model.append(name)
    row.set_model(model)
    keys = [k for k, _ in options]
    row.set_selected(keys.index(current) if current in keys else 0)
    row.keys = keys
    return row


def _switch_row(title: str, subtitle: str, active: bool) -> tuple[Adw.ActionRow, Gtk.Switch]:
    row = Adw.ActionRow(title=title, subtitle=subtitle)
    switch = Gtk.Switch(valign=Gtk.Align.CENTER, active=active)
    row.add_suffix(switch)
    row.set_activatable_widget(switch)
    return row, switch


class PreferencesWindow(Adw.PreferencesWindow):
    def __init__(self, ctx):
        super().__init__(transient_for=ctx, modal=True, title="Preferences", default_width=640, default_height=720)
        self.ctx = ctx
        s = ctx.settings
        self.connect("close-request", self._on_close)

        # --- AI page ---------------------------------------------------
        ai = Adw.PreferencesPage(title="AI", icon_name="face-smile-symbolic")
        self.add(ai)

        backend_group = Adw.PreferencesGroup(title="Who powers the other users",
                                             description="Every account except yours is played by a language model.")
        self.backend_row = _combo_row("Backend", BACKENDS, s.get("backend"))
        self.backend_row.connect("notify::selected", self._on_backend)
        backend_group.add(self.backend_row)
        test_row = Adw.ActionRow(title="Test connection", subtitle="Sends one tiny request with the settings below")
        self.test_btn = Gtk.Button(label="Test", valign=Gtk.Align.CENTER)
        self.test_btn.connect("clicked", self._test_connection)
        test_row.add_suffix(self.test_btn)
        test_row.set_activatable_widget(self.test_btn)
        backend_group.add(test_row)
        ai.add(backend_group)

        self.anthropic_group = Adw.PreferencesGroup(
            title="Claude", description="Get a key at console.anthropic.com. Claude follows Anthropic's usage policy.")
        row, self.anthropic_key = entry_row("API key", s.get("anthropic_api_key"), password=True)
        self.anthropic_group.add(row)
        row, self.anthropic_model = entry_row("Model", s.get("anthropic_model"), placeholder="claude-opus-5")
        self.anthropic_group.add(row)
        self.effort_row = _combo_row("Effort", [(e, e) for e in EFFORTS], s.get("anthropic_effort"),
                                     "Low is fast and cheap; higher effort thinks more before replying")
        self.anthropic_group.add(self.effort_row)
        ai.add(self.anthropic_group)

        self.local_group = Adw.PreferencesGroup(
            title="Local / OpenAI-compatible server",
            description="Works with Ollama, LM Studio, llama.cpp, vLLM, OpenRouter and anything that speaks "
                        "the /v1/chat/completions API. Local, uncensored models are the way to go if you want "
                        "no content restrictions at all.")
        row, self.openai_url = entry_row("Server URL", s.get("openai_base_url"), placeholder="http://localhost:11434/v1")
        self.local_group.add(row)
        row, self.openai_model = entry_row("Model", s.get("openai_model"), placeholder="llama3.1")
        self.local_group.add(row)
        row, self.openai_key = entry_row("API key (optional)", s.get("openai_api_key"), password=True)
        self.local_group.add(row)
        ai.add(self.local_group)

        image_group = Adw.PreferencesGroup(
            title="Photos", description="Optional: generate real pictures for AI posts and profile photos with a "
                                        "Stable Diffusion WebUI (AUTOMATIC1111 API). Without it, posts get abstract art.")
        row, self.imagegen_switch = _switch_row("Generate images", "Requires the WebUI running with --api",
                                                bool(s.get("imagegen_enabled")))
        image_group.add(row)
        row, self.imagegen_url = entry_row("WebUI URL", s.get("imagegen_url"), placeholder="http://127.0.0.1:7860")
        image_group.add(row)
        steps_row = Adw.ActionRow(title="Sampling steps")
        self.steps = Gtk.SpinButton.new_with_range(4, 80, 1)
        self.steps.set_value(int(s.get("imagegen_steps") or 20))
        self.steps.set_valign(Gtk.Align.CENTER)
        steps_row.add_suffix(self.steps)
        image_group.add(steps_row)
        ai.add(image_group)
        self._on_backend()

        # --- Content page ----------------------------------------------
        content = Adw.PreferencesPage(title="Content", icon_name="dialog-warning-symbolic")
        self.add(content)
        mature_group = Adw.PreferencesGroup(title="Mature content")
        row, self.age_switch = _switch_row("I'm 18 or older", "Required for mature content", bool(s.get("age_confirmed")))
        mature_group.add(row)
        row, self.mature_switch = _switch_row(
            "Allow mature content",
            "The AI users may flirt, swear and write explicit content. Nothing is filtered by the app itself; "
            "the model you chose still applies its own rules.",
            bool(s.get("mature_content")))
        self.mature_switch.set_sensitive(bool(s.get("age_confirmed")))
        self.age_switch.connect("notify::active", self._on_age)
        mature_group.add(row)
        content.add(mature_group)

        world_group = Adw.PreferencesGroup(title="The world")
        self.activity_row = _combo_row("Activity level", ACTIVITY, s.get("activity_level"),
                                       "How often people post, react and message you on their own")
        world_group.add(self.activity_row)
        content.add(world_group)

        # --- Data page -------------------------------------------------
        data = Adw.PreferencesPage(title="Data", icon_name="drive-harddisk-symbolic")
        self.add(data)
        data_group = Adw.PreferencesGroup(title="Your data", description=f"Stored locally in {ctx.data_dir}")
        reset_row = Adw.ActionRow(title="Start over", subtitle="Delete your profile, all people, posts and messages")
        reset_btn = Gtk.Button(label="Reset everything", valign=Gtk.Align.CENTER)
        reset_btn.add_css_class("destructive-action")
        reset_btn.connect("clicked", self._reset)
        reset_row.add_suffix(reset_btn)
        data_group.add(reset_row)
        data.add(data_group)

    # ------------------------------------------------------------------
    def _on_backend(self, *_):
        key = self.backend_row.keys[self.backend_row.get_selected()]
        self.anthropic_group.set_visible(key == "anthropic")
        self.local_group.set_visible(key == "openai_compat")

    def _on_age(self, *_):
        adult = self.age_switch.get_active()
        self.mature_switch.set_sensitive(adult)
        if not adult:
            self.mature_switch.set_active(False)

    def _reset(self, *_):
        def do_reset():
            self.close()
            self.ctx.reset_everything()

        confirm(self, "Reset everything?", "This deletes your profile, every person, post and message. "
                "It cannot be undone.", "Reset", do_reset)

    def _test_connection(self, *_):
        self._apply()
        self.test_btn.set_sensitive(False)
        self.test_btn.set_label("Testing…")

        def finish(text: str):
            self.test_btn.set_sensitive(True)
            self.test_btn.set_label("Test")
            self.add_toast(Adw.Toast(title=text, timeout=6))
            return False

        def work():
            try:
                backend = make_backend(self.ctx.settings)
                reply = backend.complete("You are a connection test. Reply with the single word OK.",
                                         [ChatMessage("user", "ping")], max_tokens=64)
                GLib.idle_add(finish, f"Connected. The model said: {reply[:60] or '(empty reply)'}")
            except AIError as exc:
                GLib.idle_add(finish, str(exc))
            except Exception as exc:  # noqa: BLE001
                GLib.idle_add(finish, f"Failed: {exc}")

        threading.Thread(target=work, daemon=True).start()

    def _apply(self) -> None:
        s = self.ctx.settings
        s.set("backend", self.backend_row.keys[self.backend_row.get_selected()], save=False)
        s.set("anthropic_api_key", self.anthropic_key.get_text().strip(), save=False)
        s.set("anthropic_model", self.anthropic_model.get_text().strip() or "claude-opus-5", save=False)
        s.set("anthropic_effort", EFFORTS[self.effort_row.get_selected()], save=False)
        s.set("openai_base_url", self.openai_url.get_text().strip(), save=False)
        s.set("openai_model", self.openai_model.get_text().strip(), save=False)
        s.set("openai_api_key", self.openai_key.get_text().strip(), save=False)
        s.set("imagegen_enabled", self.imagegen_switch.get_active(), save=False)
        s.set("imagegen_url", self.imagegen_url.get_text().strip() or "http://127.0.0.1:7860", save=False)
        s.set("imagegen_steps", int(self.steps.get_value()), save=False)
        s.set("age_confirmed", self.age_switch.get_active(), save=False)
        s.set("mature_content", self.mature_switch.get_active() and self.age_switch.get_active(), save=False)
        s.set("activity_level", self.activity_row.keys[self.activity_row.get_selected()], save=False)
        s.save()

    def _on_close(self, *_):
        self._apply()
        self.ctx.settings_changed()
        return False
