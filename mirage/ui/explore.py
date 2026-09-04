"""Explore: browse, search and discover people."""

from __future__ import annotations

from gi.repository import Adw, Gtk

from mirage.models import Persona
from mirage.ui.widgets import clamp, clear_box, compact_number, esc, label, make_avatar, scrolled


class PersonaCard(Gtk.Box):
    def __init__(self, ctx, persona: Persona):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.ctx = ctx
        self.persona = persona
        self.add_css_class("persona-card")
        self.set_size_request(200, -1)

        avatar = make_avatar(persona.name, persona.avatar_path, 72)
        avatar.set_halign(Gtk.Align.CENTER)
        self.append(avatar)
        self.append(label(persona.name, ("handle",), xalign=0.5))
        self.append(label(f"@{persona.handle}", ("muted", "small"), xalign=0.5))
        followers = label(f"{compact_number(persona.follower_count)} followers", ("small",), xalign=0.5)
        self.append(followers)
        bio = label(esc(persona.bio), ("small",), wrap=True, xalign=0.5, lines=2)
        bio.set_justify(Gtk.Justification.CENTER)
        self.append(bio)

        buttons = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        self.follow_btn = Gtk.Button()
        self._style_follow()
        self.follow_btn.connect("clicked", self._toggle_follow)
        buttons.append(self.follow_btn)
        msg_btn = Gtk.Button(icon_name="mail-send-symbolic")
        msg_btn.set_tooltip_text("Message")
        msg_btn.connect("clicked", lambda *_: self.ctx.open_chat(persona.id))
        buttons.append(msg_btn)
        self.append(buttons)

        click = Gtk.GestureClick()
        click.connect("released", lambda *_: self.ctx.open_persona(persona.id))
        avatar.add_controller(click)

    def _style_follow(self):
        if self.persona.followed:
            self.follow_btn.set_label("Following")
            self.follow_btn.remove_css_class("suggested-action")
        else:
            self.follow_btn.set_label("Follow")
            self.follow_btn.add_css_class("suggested-action")

    def _toggle_follow(self, *_):
        self.persona = self.ctx.toggle_follow(self.persona.id)
        self._style_follow()


class ExplorePage(Gtk.Box):
    def __init__(self, ctx):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.ctx = ctx

        top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_start=12, margin_end=12,
                      margin_top=8, margin_bottom=4)
        self.search = Gtk.SearchEntry(placeholder_text="Search people")
        self.search.connect("search-changed", lambda *_: self.reload())
        top.append(self.search)

        discover = Gtk.Box(spacing=6)
        self.hint = Gtk.Entry(placeholder_text="Optional: who are you looking for? e.g. \"a sarcastic chef from Lisbon\"")
        self.hint.set_hexpand(True)
        self.hint.connect("activate", self._discover)
        discover.append(self.hint)
        btn = Gtk.Button()
        btn.set_child(Adw.ButtonContent(icon_name="list-add-symbolic", label="Discover someone"))
        btn.add_css_class("suggested-action")
        btn.set_tooltip_text("Let the AI invent a brand-new person for your network")
        btn.connect("clicked", self._discover)
        discover.append(btn)
        top.append(discover)
        self.append(clamp(top, 900))

        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                                column_spacing=12, row_spacing=12, max_children_per_line=4,
                                margin_start=12, margin_end=12, margin_top=8, margin_bottom=24)
        self.flow.set_valign(Gtk.Align.START)
        self.append(scrolled(clamp(self.flow, 900)))

    def _discover(self, *_):
        hint = self.hint.get_text().strip()
        self.hint.set_text("")
        self.ctx.discover_persona(hint)

    def reload(self) -> None:
        clear_box(self.flow)
        for persona in self.ctx.db.list_personas(self.search.get_text()):
            self.flow.append(PersonaCard(self.ctx, persona))
