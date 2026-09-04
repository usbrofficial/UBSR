"""Activity: likes, comments, follows and new messages aimed at you."""

from __future__ import annotations

from gi.repository import Adw, Gtk

from ubsr.models import Activity
from ubsr.ui.widgets import clamp, clear_box, esc, label, make_avatar, relative_time, scrolled

VERBS = {
    "like": "liked your post",
    "comment": "commented on your post",
    "reply": "replied to your comment",
    "follow": "started following you",
    "message": "sent you a message",
}


class ActivityPage(Gtk.Box):
    def __init__(self, ctx):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.ctx = ctx
        self.list = Gtk.ListBox(margin_start=12, margin_end=12, margin_top=8, margin_bottom=24)
        self.list.add_css_class("boxed-list")
        self.list.connect("row-activated", self._on_row)
        self.empty = Adw.StatusPage(icon_name="emblem-favorite-symbolic", title="No activity yet",
                                    description="When people like, comment, follow or message you, it shows up here.")
        self.stack = Gtk.Stack()
        self.stack.add_named(self.empty, "empty")
        self.stack.add_named(scrolled(clamp(self.list, 720)), "list")
        self.append(self.stack)
        self.stack.set_vexpand(True)

    def reload(self) -> None:
        clear_box(self.list)
        items = self.ctx.db.list_activity()
        self.stack.set_visible_child_name("list" if items else "empty")
        for item in items:
            self.list.append(self._row(item))

    def _row(self, item: Activity) -> Gtk.ListBoxRow:
        persona = self.ctx.db.get_persona(item.persona_id)
        name = persona.name if persona else "Someone"
        row = Gtk.ListBoxRow()
        row.item = item
        box = Gtk.Box(spacing=12, margin_top=8, margin_bottom=8, margin_start=8, margin_end=8)
        box.append(make_avatar(name, persona.avatar_path if persona else None, 40))
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        verb = VERBS.get(item.kind, item.kind)
        headline = f"<b>{esc(name)}</b> {esc(verb)}"
        if item.text:
            headline += f": <i>{esc(item.text)}</i>"
        text.append(label(headline, markup=True, wrap=True, lines=2))
        text.append(label(relative_time(item.created_at), ("muted", "small")))
        box.append(text)
        if not item.seen:
            dot = Gtk.Label(label="new")
            dot.add_css_class("unread-dot")
            dot.set_valign(Gtk.Align.CENTER)
            box.append(dot)
        row.set_child(box)
        return row

    def _on_row(self, _list, row):
        item = row.item
        if item.kind == "message":
            self.ctx.open_chat(item.persona_id)
        elif item.kind == "follow":
            self.ctx.open_persona(item.persona_id)
        elif item.post_id:
            self.ctx.open_post(item.post_id)
