"""A single post with its full comment thread."""

from __future__ import annotations

from gi.repository import Gtk

from mirage.ui.widgets import PostCard, clamp, clear_box, label, scrolled


class PostDetailPage(Gtk.Box):
    title = "Post"

    def __init__(self, ctx, post_id: int):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.ctx = ctx
        self.post_id = post_id
        post = ctx.db.get_post(post_id)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_start=12, margin_end=12,
                            margin_top=12, margin_bottom=12)
        self.card = PostCard(ctx, post, show_comments=False)
        self.body.append(self.card)
        self.comments_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.body.append(self.comments_box)
        self.append(scrolled(clamp(self.body)))

        entry_bar = Gtk.Box(spacing=6)
        entry_bar.add_css_class("chat-entry")
        self.entry = Gtk.Entry(placeholder_text="Add a comment…", hexpand=True)
        self.entry.connect("activate", self._send)
        entry_bar.append(self.entry)
        send = Gtk.Button(icon_name="mail-send-symbolic")
        send.add_css_class("suggested-action")
        send.connect("clicked", self._send)
        entry_bar.append(send)
        self.append(clamp(entry_bar))
        self.reload_comments()

    def reload_comments(self) -> None:
        clear_box(self.comments_box)
        comments = self.ctx.db.list_comments(self.post_id)
        if comments:
            self.comments_box.append(label(f"{len(comments)} comment{'s' if len(comments) != 1 else ''}",
                                           ("muted", "small")))
        for comment in comments:
            self.comments_box.append(self.ctx.comment_label(comment))

    def refresh(self) -> None:
        self.card.refresh()
        self.reload_comments()

    def _send(self, *_):
        text = self.entry.get_text().strip()
        if not text:
            return
        self.entry.set_text("")
        self.ctx.add_my_comment(self.post_id, text)
        self.reload_comments()
