"""First-run profile creation and the profile editor."""

from __future__ import annotations

import re
from typing import Callable, Optional

from gi.repository import Adw, Gtk

from ubsr.config import APP_NAME, APP_TAGLINE
from ubsr.models import Profile
from ubsr.ui.widgets import clamp, import_media, label, make_avatar, pick_image, set_avatar_image


def clean_handle(text: str) -> str:
    return re.sub(r"[^a-z0-9._]", "", text.strip().lstrip("@").lower())[:30]


class ProfileForm(Gtk.Box):
    """Avatar picker + name / handle / bio fields."""

    def __init__(self, window: Gtk.Window, profile: Optional[Profile] = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.window = window
        self.avatar_path: Optional[str] = profile.avatar_path if profile else None

        self.avatar = make_avatar(profile.name if profile else "?", self.avatar_path, 120)
        self.avatar.set_halign(Gtk.Align.CENTER)
        avatar_btn = Gtk.Button(has_frame=False, halign=Gtk.Align.CENTER)
        avatar_btn.set_child(self.avatar)
        avatar_btn.set_tooltip_text("Choose a profile picture")
        avatar_btn.connect("clicked", self._pick_avatar)
        self.append(avatar_btn)
        change = Gtk.Button(label="Choose profile picture", has_frame=False, halign=Gtk.Align.CENTER)
        change.add_css_class("flat")
        change.add_css_class("muted")
        change.connect("clicked", self._pick_avatar)
        self.append(change)

        group = Adw.PreferencesGroup()
        self.name_entry = Gtk.Entry(placeholder_text="Your name")
        self.handle_entry = Gtk.Entry(placeholder_text="username")
        for title, entry in (("Name", self.name_entry), ("Username", self.handle_entry)):
            row = Adw.ActionRow(title=title)
            entry.set_valign(Gtk.Align.CENTER)
            entry.set_hexpand(True)
            row.add_suffix(entry)
            row.set_activatable_widget(entry)
            group.add(row)
        self.append(group)
        self.name_entry.connect("changed", lambda e: self.avatar.set_text(e.get_text() or "?"))

        self.append(label("Bio", ("muted", "small")))
        frame = Gtk.Frame()
        self.bio = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=8, bottom_margin=8, left_margin=8,
                                right_margin=8)
        self.bio.set_size_request(-1, 90)
        frame.set_child(self.bio)
        self.append(frame)

        if profile:
            self.name_entry.set_text(profile.name)
            self.handle_entry.set_text(profile.handle)
            self.bio.get_buffer().set_text(profile.bio or "")

    def _pick_avatar(self, *_):
        def picked(path):
            if not path:
                return
            stored = import_media(path, "avatar")
            if stored:
                self.avatar_path = stored
                set_avatar_image(self.avatar, stored)

        pick_image(self.window, picked, "Choose a profile picture")

    def values(self) -> Optional[tuple[str, str, str, Optional[str]]]:
        name = self.name_entry.get_text().strip()
        handle = clean_handle(self.handle_entry.get_text()) or clean_handle(name.replace(" ", ""))
        buf = self.bio.get_buffer()
        bio = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True).strip()[:200]
        if not name:
            return None
        return name, handle, bio, self.avatar_path


class OnboardingPage(Gtk.Box):
    """Full-window welcome screen shown until a profile exists."""

    def __init__(self, ctx, on_done: Callable[[str, str, str, Optional[str], bool], None]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.ctx = ctx
        self.on_done = on_done
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, margin_top=36, margin_bottom=36,
                       margin_start=24, margin_end=24)
        body.append(label(APP_NAME, ("wordmark",), xalign=0.5))
        body.append(label(APP_TAGLINE, ("tagline",), xalign=0.5))
        intro = label(
            "A photo network where everyone except you is AI. Create your profile to get started. "
            "Everything stays on this computer.", ("muted",), wrap=True, xalign=0.5)
        intro.set_margin_top(12)
        intro.set_justify(Gtk.Justification.CENTER)
        body.append(intro)
        self.form = ProfileForm(ctx)
        body.append(self.form)

        content_group = Adw.PreferencesGroup(title="Content")
        self.age_row = Adw.ActionRow(title="I'm 18 or older", subtitle="Required to enable mature content")
        self.age_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.age_row.add_suffix(self.age_switch)
        self.age_row.set_activatable_widget(self.age_switch)
        content_group.add(self.age_row)
        self.mature_row = Adw.ActionRow(title="Allow mature content",
                                        subtitle="Let the AI users flirt, swear and get explicit. You can change this later.")
        self.mature_switch = Gtk.Switch(valign=Gtk.Align.CENTER, sensitive=False)
        self.mature_row.add_suffix(self.mature_switch)
        self.mature_row.set_activatable_widget(self.mature_switch)
        content_group.add(self.mature_row)
        self.age_switch.connect("notify::active", self._on_age)
        body.append(content_group)

        self.error = label("", ("error",), xalign=0.5)
        body.append(self.error)
        go = Gtk.Button(label="Create my profile", halign=Gtk.Align.CENTER)
        go.add_css_class("suggested-action")
        go.add_css_class("pill")
        go.connect("clicked", self._done)
        body.append(go)

        sw = Gtk.ScrolledWindow(vexpand=True)
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_child(clamp(body, 520))
        self.append(sw)

    def _on_age(self, *_):
        adult = self.age_switch.get_active()
        self.mature_switch.set_sensitive(adult)
        if not adult:
            self.mature_switch.set_active(False)

    def _done(self, *_):
        values = self.form.values()
        if not values:
            self.error.set_text("Please enter a name.")
            return
        name, handle, bio, avatar = values
        self.on_done(name, handle, bio, avatar, self.age_switch.get_active(), self.mature_switch.get_active())


class EditProfileDialog(Adw.Window):
    def __init__(self, ctx, profile: Profile, on_save: Callable[[str, str, str, Optional[str]], None]):
        super().__init__(transient_for=ctx, modal=True, title="Edit profile", default_width=460, default_height=560)
        self.on_save = on_save
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(False)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: self.close())
        header.pack_start(cancel)
        save = Gtk.Button(label="Save")
        save.add_css_class("suggested-action")
        save.connect("clicked", self._save)
        header.pack_end(save)
        box.append(header)
        self.form = ProfileForm(self, profile)
        self.form.set_margin_top(16)
        self.form.set_margin_bottom(16)
        self.form.set_margin_start(16)
        self.form.set_margin_end(16)
        sw = Gtk.ScrolledWindow(vexpand=True)
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_child(self.form)
        box.append(sw)
        self.set_content(box)

    def _save(self, *_):
        values = self.form.values()
        if values:
            self.on_save(*values)
            self.close()
