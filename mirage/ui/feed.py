"""Home feed."""

from __future__ import annotations

from gi.repository import Adw, Gtk

from mirage.ui.widgets import PostCard, clamp, clear_box, scrolled


class FeedPage(Gtk.Box):
    def __init__(self, ctx):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.ctx = ctx
        self.cards: dict[int, PostCard] = {}
        self.following_only = False

        toolbar = Gtk.Box(spacing=6, margin_start=12, margin_end=12, margin_top=8, margin_bottom=4)
        self.filter_btn = Gtk.ToggleButton(label="Following")
        self.filter_btn.set_tooltip_text("Show only people you follow")
        self.filter_btn.connect("toggled", self._on_filter)
        toolbar.append(self.filter_btn)
        spacer = Gtk.Box(hexpand=True)
        toolbar.append(spacer)
        new_posts = Gtk.Button(has_frame=True)
        new_posts.set_child(Adw.ButtonContent(icon_name="view-refresh-symbolic", label="New posts"))
        new_posts.set_tooltip_text("Ask a few people to post something new")
        new_posts.connect("clicked", lambda *_: self.ctx.request_new_posts())
        toolbar.append(new_posts)
        self.append(clamp(toolbar))

        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_start=12, margin_end=12,
                            margin_top=6, margin_bottom=24)
        self.empty = Adw.StatusPage(
            icon_name="camera-photo-symbolic", title="Nothing here yet",
            description="Follow people in Explore, or press \"New posts\" to wake the feed up.",
        )
        self.empty.set_visible(False)
        self.list.append(self.empty)
        self.scroller = scrolled(clamp(self.list))
        self.append(self.scroller)

    def _on_filter(self, btn):
        self.following_only = btn.get_active()
        self.reload()

    def reload(self) -> None:
        clear_box(self.list)
        self.cards.clear()
        posts = self.ctx.db.list_feed(limit=80, followed_only=self.following_only)
        self.empty.set_visible(not posts)
        self.list.append(self.empty)
        for post in posts:
            card = PostCard(self.ctx, post)
            self.cards[post.id] = card
            self.list.append(card)

    def prepend(self, post) -> None:
        if self.following_only and post.author_type == "persona":
            persona = self.ctx.db.get_persona(post.author_id)
            if not persona or not persona.followed:
                return
        self.empty.set_visible(False)
        card = PostCard(self.ctx, post)
        self.cards[post.id] = card
        self.list.insert_child_after(card, self.empty)

    def refresh_post(self, post_id: int) -> None:
        card = self.cards.get(post_id)
        if card:
            card.refresh()

    def remove_post(self, post_id: int) -> None:
        card = self.cards.pop(post_id, None)
        if card:
            self.list.remove(card)
        if not self.cards:
            self.empty.set_visible(True)

    def scroll_top(self) -> None:
        self.scroller.get_vadjustment().set_value(0)
