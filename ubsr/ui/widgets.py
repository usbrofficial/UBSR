"""Reusable widgets and helpers shared across pages."""

from __future__ import annotations

import html
import shutil
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")

from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: E402

from ubsr.config import MEDIA_DIR  # noqa: E402
from ubsr.models import Post  # noqa: E402

# ----------------------------------------------------------------------
# Textures

_TEXTURES: "OrderedDict[tuple[str, int], Gdk.Texture]" = OrderedDict()
_MAX_CACHED = 80


def load_texture(path: Optional[str], max_size: int = 1400) -> Optional[Gdk.Texture]:
    """Load an image scaled down to ``max_size`` on its longest edge, with a small cache."""
    if not path:
        return None
    key = (path, max_size)
    if key in _TEXTURES:
        _TEXTURES.move_to_end(key)
        return _TEXTURES[key]
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, max_size, max_size, True)
        pixbuf = pixbuf.apply_embedded_orientation() or pixbuf
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
    except (GLib.Error, TypeError):
        return None
    _TEXTURES[key] = texture
    while len(_TEXTURES) > _MAX_CACHED:
        _TEXTURES.popitem(last=False)
    return texture


def forget_texture(path: Optional[str]) -> None:
    for key in [k for k in _TEXTURES if k[0] == path]:
        _TEXTURES.pop(key, None)


def import_media(source: str, prefix: str = "img") -> Optional[str]:
    """Copy a user-picked file into the media folder; returns the new path."""
    src = Path(source)
    if not src.is_file():
        return None
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    suffix = src.suffix.lower() or ".png"
    if suffix not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
        suffix = ".png"
    dest = MEDIA_DIR / f"{prefix}_{uuid.uuid4().hex[:12]}{suffix}"
    try:
        shutil.copyfile(src, dest)
    except OSError:
        return None
    return str(dest)


# ----------------------------------------------------------------------
# Small helpers

def relative_time(ts: float) -> str:
    delta = max(0, int(time.time() - ts))
    if delta < 45:
        return "just now"
    if delta < 3600:
        return f"{delta // 60}m"
    if delta < 86400:
        return f"{delta // 3600}h"
    if delta < 7 * 86400:
        return f"{delta // 86400}d"
    return time.strftime("%b %-d", time.localtime(ts))


def clock_time(ts: float) -> str:
    return time.strftime("%H:%M", time.localtime(ts))


def esc(text: str) -> str:
    return html.escape(text or "", quote=False)


def compact_number(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1000:.1f}K"
    return f"{n:,}"


def make_avatar(name: str, path: Optional[str], size: int) -> Adw.Avatar:
    avatar = Adw.Avatar(size=size, text=name or "?", show_initials=True)
    if path:
        texture = load_texture(path, max_size=max(256, size * 2))
        if texture:
            avatar.set_custom_image(texture)
    return avatar


def set_avatar_image(avatar: Adw.Avatar, path: Optional[str]) -> None:
    texture = load_texture(path, max_size=max(256, avatar.get_size() * 2)) if path else None
    avatar.set_custom_image(texture)


def make_picture(path: Optional[str], height: int = 460, cover: bool = True) -> Gtk.Picture:
    picture = Gtk.Picture()
    picture.add_css_class("post-image")
    picture.set_can_shrink(True)
    picture.set_hexpand(True)
    if cover and hasattr(picture, "set_content_fit"):
        picture.set_content_fit(Gtk.ContentFit.COVER)
        picture.set_size_request(-1, height)
    else:
        picture.set_keep_aspect_ratio(True)
    texture = load_texture(path, max_size=1000)
    if texture:
        picture.set_paintable(texture)
    return picture


def pick_image(parent: Gtk.Window, callback: Callable[[Optional[str]], None], title: str = "Choose a photo") -> None:
    """Open a native file chooser filtered to images; callback gets a path or None."""
    image_filter = Gtk.FileFilter()
    image_filter.set_name("Images")
    for mime in ("image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"):
        image_filter.add_mime_type(mime)

    if hasattr(Gtk, "FileDialog"):
        dialog = Gtk.FileDialog(title=title, modal=True)
        filters = _filter_store([image_filter])
        dialog.set_filters(filters)
        dialog.set_default_filter(image_filter)

        def done(dlg, result):
            try:
                file = dlg.open_finish(result)
            except GLib.Error:
                callback(None)
                return
            callback(file.get_path() if file else None)

        dialog.open(parent, None, done)
        return

    chooser = Gtk.FileChooserNative.new(title, parent, Gtk.FileChooserAction.OPEN, "Open", "Cancel")
    chooser.set_modal(True)
    chooser.add_filter(image_filter)

    def on_response(dlg, response):
        path = None
        if response == Gtk.ResponseType.ACCEPT:
            file = dlg.get_file()
            path = file.get_path() if file else None
        callback(path)
        dlg.destroy()

    chooser.connect("response", on_response)
    chooser.show()


def _filter_store(items):
    store = Gio.ListStore.new(Gtk.FileFilter)
    for item in items:
        store.append(item)
    return store


def confirm(parent: Gtk.Window, heading: str, body: str, ok_label: str, on_ok: Callable[[], None],
            destructive: bool = True) -> None:
    """Ask a yes/no question with the best dialog the platform offers."""
    if hasattr(Adw, "MessageDialog"):
        dialog = Adw.MessageDialog(transient_for=parent, modal=True, heading=heading, body=body)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", ok_label)
        if destructive:
            dialog.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(dlg, response):
            if response == "ok":
                on_ok()

        dialog.connect("response", on_response)
        dialog.present()
        return

    dialog = Gtk.MessageDialog(
        transient_for=parent, modal=True, message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.NONE, text=heading, secondary_text=body,
    )
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    ok = dialog.add_button(ok_label, Gtk.ResponseType.OK)
    if destructive:
        ok.add_css_class("destructive-action")

    def on_response(dlg, response):
        if response == Gtk.ResponseType.OK:
            on_ok()
        dlg.destroy()

    dialog.connect("response", on_response)
    dialog.show()


def entry_row(title: str, text: str = "", password: bool = False, placeholder: str = ""):
    """An editable preferences row; returns (row, entry-like widget with get_text/set_text)."""
    if hasattr(Adw, "PasswordEntryRow") and password:
        row = Adw.PasswordEntryRow(title=title)
        row.set_text(text or "")
        return row, row
    if hasattr(Adw, "EntryRow") and not password:
        row = Adw.EntryRow(title=title)
        row.set_text(text or "")
        return row, row
    row = Adw.ActionRow(title=title)
    entry = Gtk.PasswordEntry(show_peek_icon=True) if password else Gtk.Entry()
    entry.set_valign(Gtk.Align.CENTER)
    entry.set_hexpand(True)
    entry.set_text(text or "")
    if placeholder and not password:
        entry.set_placeholder_text(placeholder)
    row.add_suffix(entry)
    row.set_activatable_widget(entry)
    return row, entry


def scrolled(child: Gtk.Widget, vexpand: bool = True) -> Gtk.ScrolledWindow:
    sw = Gtk.ScrolledWindow(vexpand=vexpand, hexpand=True)
    sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    sw.set_child(child)
    return sw


def clamp(child: Gtk.Widget, maximum: int = 620) -> Adw.Clamp:
    c = Adw.Clamp(maximum_size=maximum, tightening_threshold=400)
    c.set_child(child)
    return c


def clear_box(box: Gtk.Widget) -> None:
    child = box.get_first_child()
    while child:
        nxt = child.get_next_sibling()
        box.remove(child)
        child = nxt


def label(text: str, css: tuple[str, ...] = (), wrap: bool = False, xalign: float = 0.0,
          markup: bool = False, lines: int = 0) -> Gtk.Label:
    lbl = Gtk.Label(xalign=xalign)
    if markup:
        lbl.set_markup(text)
    else:
        lbl.set_text(text)
    for c in css:
        lbl.add_css_class(c)
    if wrap:
        lbl.set_wrap(True)
        lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        if hasattr(lbl, "set_natural_wrap_mode"):
            lbl.set_natural_wrap_mode(Gtk.NaturalWrapMode.WORD)
    if lines:
        lbl.set_lines(lines)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
    lbl.set_hexpand(True)
    return lbl


# ----------------------------------------------------------------------
# Post card

class PostCard(Gtk.Box):
    """A feed entry: header, picture, actions, likes, caption and a comment preview."""

    def __init__(self, ctx, post: Post, show_comments: bool = True):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.ctx = ctx
        self.post = post
        self.add_css_class("post-card")
        self.show_comments = show_comments
        self._build()

    # ------------------------------------------------------------------
    def author(self):
        if self.post.is_mine:
            profile = self.ctx.db.get_profile()
            return (profile.name, profile.handle, profile.avatar_path) if profile else ("You", "you", None)
        persona = self.ctx.db.get_persona(self.post.author_id)
        if persona:
            return persona.name, persona.handle, persona.avatar_path
        return "Deleted user", "deleted", None

    def _build(self) -> None:
        clear_box(self)
        name, handle, avatar_path = self.author()
        post = self.post

        header = Gtk.Box(spacing=10)
        header.add_css_class("post-header")
        avatar = make_avatar(name, avatar_path, 34)
        header.append(avatar)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        names.append(label(name, ("handle",)))
        names.append(label(f"@{handle} · {relative_time(post.created_at)}", ("muted", "small")))
        names.set_hexpand(True)
        header.append(names)
        if not post.is_mine:
            open_btn = Gtk.Button(icon_name="go-next-symbolic", has_frame=False, valign=Gtk.Align.CENTER)
            open_btn.set_tooltip_text("View profile")
            open_btn.connect("clicked", lambda *_: self.ctx.open_persona(post.author_id))
            header.append(open_btn)
        else:
            delete_btn = Gtk.Button(icon_name="user-trash-symbolic", has_frame=False, valign=Gtk.Align.CENTER)
            delete_btn.set_tooltip_text("Delete post")
            delete_btn.connect("clicked", lambda *_: self.ctx.delete_post(post.id))
            header.append(delete_btn)
        click = Gtk.GestureClick()
        click.connect("released", lambda *_: (self.ctx.open_persona(post.author_id) if not post.is_mine else self.ctx.open_my_profile()))
        avatar.add_controller(click)
        self.append(header)

        if post.image_path:
            picture = make_picture(post.image_path)
            self.append(picture)
        else:
            caption_box = Gtk.Box()
            caption_box.add_css_class("caption-only")
            caption_box.append(label(post.caption or "…", wrap=True, xalign=0.0))
            self.append(caption_box)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        body.add_css_class("post-body")

        actions = Gtk.Box(spacing=2)
        self.like_btn = Gtk.Button(has_frame=False)
        self._update_like_button()
        self.like_btn.connect("clicked", self._on_like)
        actions.append(self.like_btn)
        comment_btn = Gtk.Button(icon_name="ubsr-comment-symbolic", has_frame=False)
        comment_btn.set_tooltip_text("Comment")
        comment_btn.connect("clicked", lambda *_: self.ctx.open_post(post.id))
        actions.append(comment_btn)
        body.append(actions)

        self.likes_label = label("", ("handle",))
        self._update_likes_label()
        body.append(self.likes_label)

        if post.image_path and post.caption:
            body.append(label(f"<b>{esc(handle)}</b> {esc(post.caption)}", wrap=True, markup=True))

        if self.show_comments:
            comments = self.ctx.db.list_comments(post.id)
            if comments:
                if len(comments) > 2:
                    more = Gtk.Button(label=f"View all {len(comments)} comments", has_frame=False, halign=Gtk.Align.START)
                    more.add_css_class("muted")
                    more.connect("clicked", lambda *_: self.ctx.open_post(post.id))
                    body.append(more)
                for comment in comments[-2:]:
                    body.append(self.ctx.comment_label(comment))
        self.append(body)

    def _update_like_button(self) -> None:
        liked = self.post.liked_by_me
        self.like_btn.set_icon_name("ubsr-heart-symbolic" if liked else "ubsr-heart-outline-symbolic")
        if liked:
            self.like_btn.add_css_class("liked")
        else:
            self.like_btn.remove_css_class("liked")
        self.like_btn.set_tooltip_text("Unlike" if liked else "Like")

    def _update_likes_label(self) -> None:
        n = self.post.like_count
        self.likes_label.set_text(f"{compact_number(n)} like{'s' if n != 1 else ''}")

    def _on_like(self, *_):
        self.post = self.ctx.toggle_like(self.post.id)
        self._update_like_button()
        self._update_likes_label()

    def refresh(self, post: Optional[Post] = None) -> None:
        self.post = post or self.ctx.db.get_post(self.post.id) or self.post
        self._build()
