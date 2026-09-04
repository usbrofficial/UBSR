"""Profile pages for you and for the AI personas."""

from __future__ import annotations

from typing import Optional

from gi.repository import Gtk

from ubsr.models import Persona, Post, Profile
from ubsr.ui.widgets import (clamp, clear_box, compact_number, esc, label, load_texture, make_avatar,
                               scrolled)


class PostGrid(Gtk.FlowBox):
    def __init__(self, ctx, posts: list[Post]):
        super().__init__(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, column_spacing=6,
                         row_spacing=6, max_children_per_line=3, min_children_per_line=3)
        self.ctx = ctx
        self.set_valign(Gtk.Align.START)
        self.set_posts(posts)

    def set_posts(self, posts: list[Post]) -> None:
        clear_box(self)
        for post in posts:
            self.append(self._thumb(post))

    def _thumb(self, post: Post) -> Gtk.Widget:
        button = Gtk.Button(has_frame=False)
        button.add_css_class("grid-thumb")
        button.set_size_request(120, 160)
        if post.image_path:
            pic = Gtk.Picture()
            pic.set_can_shrink(True)
            if hasattr(pic, "set_content_fit"):
                pic.set_content_fit(Gtk.ContentFit.COVER)
            texture = load_texture(post.image_path, max_size=600)
            if texture:
                pic.set_paintable(texture)
            pic.set_size_request(-1, 160)
            button.set_child(pic)
        else:
            lbl = label(esc(post.caption), ("small",), wrap=True, xalign=0.5, lines=5)
            lbl.set_justify(Gtk.Justification.CENTER)
            lbl.set_margin_start(8)
            lbl.set_margin_end(8)
            button.set_child(lbl)
        button.connect("clicked", lambda *_: self.ctx.open_post(post.id))
        return button


def _stat(number: str, caption: str) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    box.append(label(number, ("profile-stat-number",), xalign=0.5))
    box.append(label(caption, ("muted", "small"), xalign=0.5))
    return box


class ProfileHeader(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=18, margin_bottom=8,
                         margin_start=16, margin_end=16)
        self.top = Gtk.Box(spacing=20)
        self.avatar_slot = Gtk.Box()
        self.top.append(self.avatar_slot)
        self.stats = Gtk.Box(spacing=28, hexpand=True, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.top.append(self.stats)
        self.append(self.top)
        self.name = label("", ("title-3",))
        self.append(self.name)
        self.handle = label("", ("muted",))
        self.append(self.handle)
        self.bio = label("", (), wrap=True)
        self.append(self.bio)
        self.buttons = Gtk.Box(spacing=8, margin_top=6)
        self.append(self.buttons)

    def fill(self, name: str, handle: str, bio: str, avatar_path: Optional[str], stats: list[tuple[str, str]]):
        clear_box(self.avatar_slot)
        self.avatar_slot.append(make_avatar(name, avatar_path, 96))
        clear_box(self.stats)
        for number, caption in stats:
            self.stats.append(_stat(number, caption))
        self.name.set_text(name)
        self.handle.set_text(f"@{handle}")
        self.bio.set_text(bio)
        self.bio.set_visible(bool(bio))


class MyProfilePage(Gtk.Box):
    title = "Profile"

    def __init__(self, ctx):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.ctx = ctx
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_bottom=24)
        self.header = ProfileHeader()
        edit = Gtk.Button(label="Edit profile")
        edit.add_css_class("outline")
        edit.connect("clicked", lambda *_: self.ctx.edit_profile())
        self.header.buttons.append(edit)
        prefs = Gtk.Button(label="Preferences")
        prefs.add_css_class("flat")
        prefs.connect("clicked", lambda *_: self.ctx.open_preferences())
        self.header.buttons.append(prefs)
        body.append(self.header)
        body.append(Gtk.Separator(margin_top=8, margin_bottom=8))
        self.grid = PostGrid(ctx, [])
        self.grid.set_margin_start(12)
        self.grid.set_margin_end(12)
        body.append(self.grid)
        self.empty = label("Share your first post with the + button.", ("muted",), xalign=0.5)
        self.empty.set_margin_top(24)
        body.append(self.empty)
        self.append(scrolled(clamp(body, 760)))

    def reload(self) -> None:
        profile: Optional[Profile] = self.ctx.db.get_profile()
        if not profile:
            return
        posts = self.ctx.db.list_posts_by("me", 0)
        personas = self.ctx.db.list_personas()
        followers = sum(1 for p in personas if p.follows_me)
        following = sum(1 for p in personas if p.followed)
        self.header.fill(profile.name, profile.handle, profile.bio, profile.avatar_path, [
            (str(len(posts)), "posts"), (str(followers), "followers"), (str(following), "following"),
        ])
        self.grid.set_posts(posts)
        self.empty.set_visible(not posts)


class PersonaProfilePage(Gtk.Box):
    def __init__(self, ctx, persona_id: int):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.ctx = ctx
        self.persona_id = persona_id
        self.title = "Profile"
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_bottom=24)
        self.header = ProfileHeader()
        self.follow_btn = Gtk.Button()
        self.follow_btn.connect("clicked", self._toggle_follow)
        self.header.buttons.append(self.follow_btn)
        msg = Gtk.Button(label="Message")
        msg.add_css_class("outline")
        msg.connect("clicked", lambda *_: self.ctx.open_chat(self.persona_id))
        self.header.buttons.append(msg)
        remove = Gtk.Button(label="Remove", has_frame=False)
        remove.add_css_class("flat")
        remove.add_css_class("muted")
        remove.set_tooltip_text("Remove this person from your network")
        remove.connect("clicked", lambda *_: self.ctx.delete_persona(self.persona_id))
        self.header.buttons.append(remove)
        body.append(self.header)
        self.interests = label("", ("muted", "small"), wrap=True)
        self.interests.set_margin_start(16)
        self.interests.set_margin_end(16)
        body.append(self.interests)
        body.append(Gtk.Separator(margin_top=8, margin_bottom=8))
        self.grid = PostGrid(ctx, [])
        self.grid.set_margin_start(12)
        self.grid.set_margin_end(12)
        body.append(self.grid)
        self.append(scrolled(clamp(body, 760)))
        self.reload()

    def reload(self) -> None:
        persona: Optional[Persona] = self.ctx.db.get_persona(self.persona_id)
        if not persona:
            return
        self.title = persona.name
        posts = self.ctx.db.list_posts_by("persona", persona.id)
        following = 80 + (persona.follower_count // 23) % 900
        self.header.fill(persona.name, persona.handle, persona.bio, persona.avatar_path, [
            (str(len(posts)), "posts"),
            (compact_number(persona.follower_count + (1 if persona.followed else 0)), "followers"),
            (str(following), "following"),
        ])
        self.interests.set_text("Into: " + ", ".join(persona.interests) if persona.interests else "")
        if persona.follows_me:
            self.header.handle.set_text(f"@{persona.handle} · follows you")
        self._style_follow(persona)
        self.grid.set_posts(posts)

    def _style_follow(self, persona: Persona):
        if persona.followed:
            self.follow_btn.set_label("Following")
            self.follow_btn.remove_css_class("suggested-action")
            self.follow_btn.add_css_class("outline")
        else:
            self.follow_btn.set_label("Follow")
            self.follow_btn.remove_css_class("outline")
            self.follow_btn.add_css_class("suggested-action")

    def _toggle_follow(self, *_):
        self.ctx.toggle_follow(self.persona_id)
        self.reload()
