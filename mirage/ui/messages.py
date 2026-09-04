"""Direct messages: conversation list plus chat view."""

from __future__ import annotations

from typing import Optional

from gi.repository import Adw, GLib, Gtk

from mirage.models import Conversation, Message
from mirage.ui.widgets import (clear_box, clock_time, esc, import_media, label, make_avatar, make_picture,
                               pick_image, relative_time, scrolled)


class ConversationRow(Gtk.ListBoxRow):
    def __init__(self, ctx, conv: Conversation):
        super().__init__()
        self.conversation_id = conv.id
        self.persona_id = conv.persona_id
        persona = ctx.db.get_persona(conv.persona_id)
        name = persona.name if persona else "Deleted user"
        box = Gtk.Box(spacing=10)
        box.add_css_class("conversation-row")
        box.append(make_avatar(name, persona.avatar_path if persona else None, 44))
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        top = Gtk.Box(spacing=6)
        top.append(label(name, ("handle",) if conv.unread else ()))
        top.append(label(relative_time(conv.last_message_at), ("muted", "small"), xalign=1.0))
        text.append(top)
        preview = label(conv.last_text.replace("\n", " ") or "Say hi", ("small",) + (() if conv.unread else ("muted",)),
                        lines=1)
        text.append(preview)
        text.set_hexpand(True)
        box.append(text)
        if conv.unread:
            badge = Gtk.Label(label=str(conv.unread))
            badge.add_css_class("unread-dot")
            badge.set_valign(Gtk.Align.CENTER)
            box.append(badge)
        self.set_child(box)


class ChatView(Gtk.Box):
    def __init__(self, ctx):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.ctx = ctx
        self.conversation: Optional[Conversation] = None
        self.persona = None
        self._pending_image: Optional[str] = None

        # header
        self.header = Gtk.Box(spacing=10, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
        self.avatar = make_avatar("?", None, 36)
        self.header.append(self.avatar)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.name_label = label("", ("handle",))
        self.status_label = label("", ("muted", "small"))
        names.append(self.name_label)
        names.append(self.status_label)
        names.set_hexpand(True)
        self.header.append(names)
        profile_btn = Gtk.Button(icon_name="avatar-default-symbolic", has_frame=False)
        profile_btn.set_tooltip_text("View profile")
        profile_btn.connect("clicked", lambda *_: self.persona and self.ctx.open_persona(self.persona.id))
        self.header.append(profile_btn)
        self.append(self.header)
        self.append(Gtk.Separator())

        # messages
        self.messages_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_start=12,
                                    margin_end=12, margin_top=12, margin_bottom=12, valign=Gtk.Align.END)
        self.scroller = scrolled(self.messages_box)
        self.append(self.scroller)
        self.typing_label = label("", ("typing-indicator",))
        self.typing_label.set_visible(False)
        self.append(self.typing_label)

        # entry
        entry_bar = Gtk.Box(spacing=6)
        entry_bar.add_css_class("chat-entry")
        self.attach_btn = Gtk.Button(icon_name="image-x-generic-symbolic", has_frame=False)
        self.attach_btn.set_tooltip_text("Send a photo")
        self.attach_btn.connect("clicked", self._attach)
        entry_bar.append(self.attach_btn)
        self.entry = Gtk.Entry(placeholder_text="Message…", hexpand=True)
        self.entry.connect("activate", self._send)
        entry_bar.append(self.entry)
        self.send_btn = Gtk.Button(icon_name="mail-send-symbolic")
        self.send_btn.add_css_class("suggested-action")
        self.send_btn.connect("clicked", self._send)
        entry_bar.append(self.send_btn)
        self.append(entry_bar)

        self.placeholder = Adw.StatusPage(icon_name="mail-unread-symbolic", title="Your messages",
                                          description="Pick a conversation, or message someone from their profile.")

    # ------------------------------------------------------------------
    def show_conversation(self, conv: Conversation) -> None:
        self.conversation = conv
        self.persona = self.ctx.db.get_persona(conv.persona_id)
        name = self.persona.name if self.persona else "Deleted user"
        self.name_label.set_text(name)
        self.status_label.set_text(f"@{self.persona.handle}" if self.persona else "")
        self.avatar.set_text(name)
        from mirage.ui.widgets import set_avatar_image

        set_avatar_image(self.avatar, self.persona.avatar_path if self.persona else None)
        self.typing_label.set_visible(False)
        self.reload_messages()
        self.entry.grab_focus()

    def reload_messages(self) -> None:
        clear_box(self.messages_box)
        if not self.conversation:
            return
        for msg in self.ctx.db.list_messages(self.conversation.id):
            self.messages_box.append(self._bubble(msg))
        self._scroll_bottom()

    def append_message(self, msg: Message) -> None:
        if self.conversation and msg.conversation_id == self.conversation.id:
            self.messages_box.append(self._bubble(msg))
            self._scroll_bottom()

    def set_typing(self, typing: bool) -> None:
        if not self.persona:
            return
        self.typing_label.set_text(f"{self.persona.name} is typing…")
        self.typing_label.set_visible(typing)
        if typing:
            self._scroll_bottom()

    def _bubble(self, msg: Message) -> Gtk.Widget:
        mine = msg.sender == "me"
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                      halign=Gtk.Align.END if mine else Gtk.Align.START)
        if msg.image_path:
            pic = make_picture(msg.image_path, height=260, cover=False)
            pic.set_size_request(120, -1)
            pic.set_halign(Gtk.Align.END if mine else Gtk.Align.START)
            frame = Gtk.Frame()
            frame.set_child(pic)
            frame.add_css_class("grid-thumb")
            frame.set_size_request(-1, -1)
            row.append(frame)
        if msg.text:
            bubble = label(esc(msg.text), ("bubble", "bubble-me" if mine else "bubble-them"), wrap=True,
                           markup=True)
            bubble.set_selectable(True)
            bubble.set_max_width_chars(48)
            bubble.set_hexpand(False)
            bubble.set_xalign(0.0)
            row.append(bubble)
        stamp = label(clock_time(msg.created_at), ("bubble-time",), xalign=1.0 if mine else 0.0)
        stamp.set_hexpand(False)
        row.append(stamp)
        return row

    def _scroll_bottom(self) -> None:
        def go():
            adj = self.scroller.get_vadjustment()
            adj.set_value(adj.get_upper() - adj.get_page_size())
            return False

        GLib.idle_add(go)

    def _attach(self, *_):
        def picked(path):
            if not path:
                return
            stored = import_media(path, "dm")
            if stored and self.conversation:
                self.ctx.send_dm(self.conversation.id, "", stored)

        pick_image(self.ctx, picked)

    def _send(self, *_):
        text = self.entry.get_text().strip()
        if not text or not self.conversation:
            return
        self.entry.set_text("")
        self.ctx.send_dm(self.conversation.id, text, None)


class MessagesPage(Gtk.Box):
    def __init__(self, ctx):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.ctx = ctx
        self.rows: dict[int, ConversationRow] = {}
        self.current_id: Optional[int] = None

        self.leaflet = Adw.Leaflet(can_navigate_back=True, can_unfold=True)
        self.leaflet.set_transition_type(Adw.LeafletTransitionType.SLIDE)

        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar.set_size_request(280, -1)
        self.list = Gtk.ListBox()
        self.list.add_css_class("navigation-sidebar")
        self.list.connect("row-activated", self._on_row)
        self.list_empty = Adw.StatusPage(icon_name="mail-unread-symbolic", title="No conversations",
                                         description="Message someone from Explore or their profile.")
        self.list_empty.set_vexpand(True)
        self.sidebar_stack = Gtk.Stack()
        self.sidebar_stack.add_named(self.list_empty, "empty")
        self.sidebar_stack.add_named(scrolled(self.list), "list")
        sidebar.append(self.sidebar_stack)
        self.sidebar_stack.set_vexpand(True)
        self.leaflet.append(sidebar).set_name("list")
        self.leaflet.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)).set_navigatable(False)

        self.chat = ChatView(ctx)
        self.chat_stack = Gtk.Stack(hexpand=True)
        self.chat_stack.add_named(self.chat.placeholder, "placeholder")
        self.chat_stack.add_named(self.chat, "chat")
        self.leaflet.append(self.chat_stack).set_name("chat")
        self.leaflet.set_visible_child_name("list")
        self.leaflet.connect("notify::folded", lambda *_: self.ctx.update_header())
        self.leaflet.connect("notify::visible-child", lambda *_: self.ctx.update_header())
        self.append(self.leaflet)
        self.leaflet.set_vexpand(True)

    # ------------------------------------------------------------------
    def reload(self) -> None:
        clear_box(self.list)
        self.rows.clear()
        convs = self.ctx.db.list_conversations()
        self.sidebar_stack.set_visible_child_name("list" if convs else "empty")
        for conv in convs:
            row = ConversationRow(self.ctx, conv)
            self.rows[conv.id] = row
            self.list.append(row)
            if conv.id == self.current_id:
                self.list.select_row(row)

    def open_conversation(self, conversation_id: int) -> None:
        conv = self.ctx.db.get_conversation(conversation_id)
        if not conv:
            return
        self.current_id = conversation_id
        self.ctx.db.mark_conversation_read(conversation_id)
        self.chat.show_conversation(conv)
        self.chat_stack.set_visible_child_name("chat")
        self.leaflet.set_visible_child_name("chat")
        self.reload()
        self.ctx.update_badges()

    def _on_row(self, _list, row: ConversationRow):
        self.open_conversation(row.conversation_id)

    def on_message(self, payload: dict) -> None:
        msg: Message = payload["message"]
        if self.current_id == msg.conversation_id and self.ctx.is_viewing_chat():
            self.chat.append_message(msg)
            self.ctx.db.mark_conversation_read(msg.conversation_id)
        self.reload()

    def on_typing(self, payload: dict) -> None:
        if self.current_id == payload["conversation_id"]:
            self.chat.set_typing(bool(payload["typing"]))

    @property
    def showing_folded_chat(self) -> bool:
        return self.leaflet.get_folded() and self.leaflet.get_visible_child_name() == "chat"

    def go_back_to_list(self) -> bool:
        if self.showing_folded_chat:
            self.leaflet.set_visible_child_name("list")
            return True
        return False
