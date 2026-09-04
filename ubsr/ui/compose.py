"""Dialog for creating a new post."""

from __future__ import annotations

from typing import Optional

from gi.repository import Adw, Gtk

from ubsr.ui.widgets import import_media, load_texture, pick_image


class ComposeDialog(Adw.Window):
    def __init__(self, ctx):
        super().__init__(transient_for=ctx, modal=True, title="New post", default_width=520, default_height=640)
        self.ctx = ctx
        self.image_path: Optional[str] = None

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(False)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: self.close())
        header.pack_start(cancel)
        self.share = Gtk.Button(label="Share")
        self.share.add_css_class("suggested-action")
        self.share.connect("clicked", self._share)
        header.pack_end(self.share)
        box.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=12, margin_bottom=12,
                          margin_start=16, margin_end=16)
        self.picture = Gtk.Picture()
        self.picture.set_can_shrink(True)
        self.picture.set_size_request(-1, 300)
        if hasattr(self.picture, "set_content_fit"):
            self.picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.picture.add_css_class("post-image")
        self.picture.set_visible(False)
        content.append(self.picture)

        self.pick_btn = Gtk.Button(label="Choose a photo")
        self.pick_btn.add_css_class("outline")
        self.pick_btn.set_halign(Gtk.Align.CENTER)
        self.pick_btn.connect("clicked", self._pick)
        content.append(self.pick_btn)

        frame = Gtk.Frame()
        self.caption = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=8, bottom_margin=8,
                                    left_margin=8, right_margin=8)
        self.caption.set_size_request(-1, 140)
        self.caption.set_vexpand(True)
        frame.set_child(self.caption)
        content.append(Gtk.Label(label="Caption", xalign=0.0, css_classes=["muted", "small"]))
        content.append(frame)
        box.append(content)
        self.set_content(box)
        self.caption.grab_focus()

    def _pick(self, *_):
        def picked(path):
            if not path:
                return
            stored = import_media(path, "post")
            if not stored:
                self.ctx.toast("Couldn't read that image.")
                return
            self.image_path = stored
            texture = load_texture(stored)
            self.picture.set_paintable(texture)
            self.picture.set_visible(texture is not None)
            self.pick_btn.set_label("Change photo")

        pick_image(self, picked)

    def _share(self, *_):
        buf = self.caption.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True).strip()
        if not text and not self.image_path:
            self.ctx.toast("Add a photo or a caption first.")
            return
        self.ctx.create_post(text, self.image_path)
        self.close()
