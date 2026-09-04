"""Main application window. Also serves as the shared context object for pages."""

from __future__ import annotations

from typing import Optional

from gi.repository import Adw, Gio, GLib, GObject, Gtk

from ubsr.config import APP_NAME, DATA_DIR
from ubsr.models import Comment
from ubsr.ui.activity import ActivityPage
from ubsr.ui.compose import ComposeDialog
from ubsr.ui.explore import ExplorePage
from ubsr.ui.feed import FeedPage
from ubsr.ui.messages import MessagesPage
from ubsr.ui.onboarding import EditProfileDialog, OnboardingPage
from ubsr.ui.post_detail import PostDetailPage
from ubsr.ui.profile import MyProfilePage, PersonaProfilePage
from ubsr.ui.settings import PreferencesWindow
from ubsr.ui.widgets import confirm, esc, forget_texture, label


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app, db, settings, world):
        super().__init__(application=app, title="UBSR")
        self.app = app
        self.db = db
        self.settings = settings
        self.world = world
        self.data_dir = DATA_DIR
        self.set_default_size(int(settings.get("window_width") or 1100), int(settings.get("window_height") or 760))
        self.set_size_request(360, 500)
        self._pages: list[Gtk.Widget] = []

        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)
        self.root_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.toast_overlay.set_child(self.root_stack)

        # Onboarding -----------------------------------------------------
        self.onboarding = OnboardingPage(self, self._finish_onboarding)
        onboarding_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        ob_header = Adw.HeaderBar()
        ob_header.set_title_widget(label(APP_NAME, ("brand",), xalign=0.5))
        onboarding_box.append(ob_header)
        onboarding_box.append(self.onboarding)
        self.root_stack.add_named(onboarding_box, "onboarding")

        # Main -----------------------------------------------------------
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.header = Adw.HeaderBar()
        self.back_btn = Gtk.Button(icon_name="go-previous-symbolic", visible=False)
        self.back_btn.connect("clicked", lambda *_: self.pop_page())
        self.header.pack_start(self.back_btn)
        self.compose_btn = Gtk.Button(icon_name="list-add-symbolic")
        self.compose_btn.set_tooltip_text("New post")
        self.compose_btn.connect("clicked", lambda *_: self.compose())
        self.header.pack_end(self.compose_btn)
        menu = Gio.Menu()
        menu.append("Preferences", "app.preferences")
        menu.append("About UBSR", "app.about")
        menu.append("Quit", "app.quit")
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        self.header.pack_end(menu_btn)
        self.spinner = Gtk.Spinner()
        self.spinner.set_tooltip_text("The AI is thinking…")
        self.header.pack_end(self.spinner)
        main.append(self.header)

        self.nav = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, vexpand=True)
        main.append(self.nav)

        tabs = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.view_stack = Adw.ViewStack(vexpand=True)
        self.feed = FeedPage(self)
        self.explore = ExplorePage(self)
        self.activity = ActivityPage(self)
        self.messages = MessagesPage(self)
        self.profile = MyProfilePage(self)
        self.pages = {
            "feed": self.view_stack.add_titled(self.feed, "feed", "Home"),
            "explore": self.view_stack.add_titled(self.explore, "explore", "Explore"),
            "activity": self.view_stack.add_titled(self.activity, "activity", "Activity"),
            "messages": self.view_stack.add_titled(self.messages, "messages", "Messages"),
            "profile": self.view_stack.add_titled(self.profile, "profile", "Profile"),
        }
        for name, icon in (("feed", "go-home-symbolic"), ("explore", "system-search-symbolic"),
                           ("activity", "emblem-favorite-symbolic"), ("messages", "mail-unread-symbolic"),
                           ("profile", "avatar-default-symbolic")):
            self.pages[name].set_icon_name(icon)
        self.view_stack.connect("notify::visible-child", self._on_tab_changed)
        tabs.append(self.view_stack)
        self.switcher_bar = Adw.ViewSwitcherBar(stack=self.view_stack)
        tabs.append(self.switcher_bar)
        self.nav.add_named(tabs, "root")

        self.switcher_title = Adw.ViewSwitcherTitle(stack=self.view_stack, title=APP_NAME)
        self.switcher_title.bind_property("title-visible", self.switcher_bar, "reveal",
                                          GObject.BindingFlags.SYNC_CREATE)
        self.page_title = Adw.WindowTitle(title="")
        self.header.set_title_widget(self.switcher_title)
        self.root_stack.add_named(main, "main")

        # Keyboard: Escape goes back
        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key)
        self.add_controller(key)
        self.connect("close-request", self._on_close)

        self.world.connect("event", self._on_world_event)
        if self.db.get_profile() is None:
            self.root_stack.set_visible_child_name("onboarding")
        else:
            self.root_stack.set_visible_child_name("main")
            self.reload_all()

    # ------------------------------------------------------------------
    # navigation
    def push_page(self, page: Gtk.Widget) -> None:
        name = f"page{len(self._pages)}"
        self._pages.append(page)
        self.nav.add_named(page, name)
        self.nav.set_visible_child(page)
        self._update_header()

    def pop_page(self) -> None:
        if not self._pages:
            self.messages.go_back_to_list()
            return
        page = self._pages.pop()
        target = self._pages[-1] if self._pages else self.nav.get_child_by_name("root")
        self.nav.set_visible_child(target)
        GLib.timeout_add(350, lambda: (self.nav.remove(page), False)[1])
        self._update_header()

    def pop_all(self) -> None:
        while self._pages:
            page = self._pages.pop()
            self.nav.remove(page)
        self.nav.set_visible_child_name("root")
        self._update_header()

    def update_header(self) -> None:
        self._update_header()

    def _update_header(self) -> None:
        if self._pages:
            self.back_btn.set_visible(True)
            self.page_title.set_title(getattr(self._pages[-1], "title", ""))
            self.header.set_title_widget(self.page_title)
        else:
            folded_chat = (self.view_stack.get_visible_child_name() == "messages"
                           and self.messages.showing_folded_chat)
            self.back_btn.set_visible(folded_chat)
            self.header.set_title_widget(self.switcher_title)

    def _on_key(self, _ctrl, keyval, _keycode, _state):
        from gi.repository import Gdk

        if keyval == Gdk.KEY_Escape and self.root_stack.get_visible_child_name() == "main":
            self.pop_page()
            return True
        return False

    def _on_tab_changed(self, *_):
        name = self.view_stack.get_visible_child_name()
        self._update_header()
        if name == "activity":
            self.db.mark_activity_seen()
            self.activity.reload()
            self.update_badges()
        elif name == "messages" and self.messages.current_id:
            self.db.mark_conversation_read(self.messages.current_id)
            self.update_badges()

    def is_viewing_chat(self) -> bool:
        return (not self._pages and self.view_stack.get_visible_child_name() == "messages"
                and self.is_active())

    # ------------------------------------------------------------------
    # helpers used by pages
    def toast(self, text: str, button: Optional[str] = None, action: Optional[str] = None, timeout: int = 4) -> None:
        toast = Adw.Toast(title=text, timeout=timeout)
        if button and action:
            toast.set_button_label(button)
            toast.set_action_name(action)
        self.toast_overlay.add_toast(toast)

    def comment_label(self, comment: Comment) -> Gtk.Widget:
        if comment.author_type == "me":
            profile = self.db.get_profile()
            handle = profile.handle if profile else "you"
        else:
            persona = self.db.get_persona(comment.author_id)
            handle = persona.handle if persona else "deleted"
        lbl = label(f"<b>{esc(handle)}</b> {esc(comment.text)}", wrap=True, markup=True)
        lbl.add_css_class("comment-row")
        lbl.set_selectable(True)
        lbl.set_can_focus(False)
        return lbl

    def reload_all(self) -> None:
        self.feed.reload()
        self.explore.reload()
        self.activity.reload()
        self.messages.reload()
        self.profile.reload()
        self.update_badges()
        self.world.ensure_avatars()

    def update_badges(self) -> None:
        unread = self.db.total_unread()
        unseen = self.db.unseen_activity()
        for name, count in (("messages", unread), ("activity", unseen)):
            page = self.pages[name]
            if hasattr(page, "set_badge_number"):
                page.set_badge_number(count)
            page.set_needs_attention(count > 0)

    # ------------------------------------------------------------------
    # actions
    def _finish_onboarding(self, name, handle, bio, avatar, adult, mature):
        self.db.save_profile(name, handle, bio, avatar)
        self.settings.set("age_confirmed", bool(adult), save=False)
        self.settings.set("mature_content", bool(mature and adult), save=False)
        self.settings.set("onboarded", True)
        self.root_stack.set_visible_child_name("main")
        self.reload_all()
        if not self.world.configured:
            self.toast("Add an AI backend in Preferences so the other users come alive.", "Preferences",
                       "app.preferences", timeout=8)

    def edit_profile(self) -> None:
        profile = self.db.get_profile()
        if not profile:
            return

        def save(name, handle, bio, avatar):
            self.db.save_profile(name, handle, bio, avatar)
            forget_texture(avatar)
            self.profile.reload()
            self.feed.reload()
            self.toast("Profile updated.")

        EditProfileDialog(self, profile, save).present()

    def open_preferences(self) -> None:
        PreferencesWindow(self).present()

    def settings_changed(self) -> None:
        self.world.reload_backend()
        if self.world.configured:
            self.toast("AI backend ready.")
            self.world.ensure_avatars()
        elif self.world.configuration_problem:
            self.toast(self.world.configuration_problem, timeout=6)

    def compose(self) -> None:
        ComposeDialog(self).present()

    def create_post(self, caption: str, image_path: Optional[str]) -> None:
        post = self.db.add_post("me", 0, caption, image_path)
        self.feed.prepend(post)
        self.profile.reload()
        self.view_stack.set_visible_child_name("feed")
        self.pop_all()
        self.feed.scroll_top()
        self.world.user_posted(post.id)
        self.toast("Posted.")

    def delete_post(self, post_id: int) -> None:
        def do_delete():
            self.db.delete_post(post_id)
            self.feed.remove_post(post_id)
            self.profile.reload()
            if self._pages and isinstance(self._pages[-1], PostDetailPage) and self._pages[-1].post_id == post_id:
                self.pop_page()

        confirm(self, "Delete this post?", "Comments and likes on it go too.", "Delete", do_delete)

    def toggle_like(self, post_id: int):
        post = self.db.get_post(post_id)
        if not post:
            return None
        return self.db.set_liked_by_me(post_id, not post.liked_by_me)

    def add_my_comment(self, post_id: int, text: str) -> None:
        post = self.db.get_post(post_id)
        if not post:
            return
        comment = self.db.add_comment(post_id, "me", 0, text)
        self.feed.refresh_post(post_id)
        self.world.user_commented(post, comment)

    def toggle_follow(self, persona_id: int):
        persona = self.db.get_persona(persona_id)
        if not persona:
            return None
        self.db.set_followed(persona_id, not persona.followed)
        if not persona.followed:
            self.world.user_followed(persona_id)
        self.explore.reload()
        self.profile.reload()
        if self.feed.following_only:
            self.feed.reload()
        return self.db.get_persona(persona_id)

    def open_persona(self, persona_id: int) -> None:
        if self._pages and isinstance(self._pages[-1], PersonaProfilePage) and self._pages[-1].persona_id == persona_id:
            return
        self.push_page(PersonaProfilePage(self, persona_id))

    def open_my_profile(self) -> None:
        self.pop_all()
        self.view_stack.set_visible_child_name("profile")

    def open_post(self, post_id: int) -> None:
        if not self.db.get_post(post_id):
            self.toast("That post is gone.")
            return
        self.push_page(PostDetailPage(self, post_id))

    def open_chat(self, persona_id: int) -> None:
        conv = self.db.get_or_create_conversation(persona_id)
        self.pop_all()
        self.view_stack.set_visible_child_name("messages")
        self.messages.open_conversation(conv.id)

    def send_dm(self, conversation_id: int, text: str, image_path: Optional[str]) -> None:
        msg = self.db.add_message(conversation_id, "me", text, image_path)
        self.messages.chat.append_message(msg)
        self.messages.reload()
        self.world.user_sent_dm(conversation_id)

    def request_new_posts(self) -> None:
        if not self.world.configured:
            self._not_configured(self.world.configuration_problem)
            return
        self.world.refresh_feed(3)
        self.toast("Asked a few people to post something…")

    def discover_persona(self, hint: str) -> None:
        if not self.world.configured:
            self._not_configured(self.world.configuration_problem)
            return
        self.world.discover_persona(hint)
        self.toast("Inventing someone new…")

    def delete_persona(self, persona_id: int) -> None:
        persona = self.db.get_persona(persona_id)
        if not persona:
            return

        def do_delete():
            self.db.delete_persona(persona_id)
            self.pop_all()
            self.reload_all()
            self.toast(f"{persona.name} is gone.")

        confirm(self, f"Remove {persona.name}?", "Their posts, comments and your conversation are deleted.",
                "Remove", do_delete)

    def reset_everything(self) -> None:
        self.db.wipe_everything()
        from ubsr.personas import seed_database
        from ubsr.config import MEDIA_DIR

        seed_database(self.db, MEDIA_DIR)
        self.settings.set("onboarded", False)
        self.pop_all()
        self.root_stack.set_visible_child_name("onboarding")

    def _not_configured(self, problem: Optional[str]) -> None:
        self.toast(problem or "Set up an AI backend in Preferences first.", "Preferences", "app.preferences",
                   timeout=8)

    # ------------------------------------------------------------------
    # world events (already on the main loop)
    def _on_world_event(self, _world, kind: str, payload) -> None:
        if kind == "busy":
            self.spinner.set_spinning(bool(payload))
            self.spinner.set_visible(bool(payload))
        elif kind == "error":
            self.toast(str(payload), timeout=6)
        elif kind == "not_configured":
            self._not_configured(payload)
        elif kind == "post_created":
            self.feed.prepend(payload)
            persona = self.db.get_persona(payload.author_id)
            if persona:
                self.toast(f"{persona.name} posted something new.")
            self._refresh_persona_page(payload.author_id)
        elif kind == "like":
            post = payload["post"]
            self.feed.refresh_post(post.id)
            self._refresh_post_page(post.id)
            if post.is_mine:
                self.activity.reload()
                self.update_badges()
        elif kind == "comment_created":
            post = payload["post"]
            self.feed.refresh_post(post.id)
            self._refresh_post_page(post.id)
            if post.is_mine:
                self.activity.reload()
                self.update_badges()
                self.toast(f"{payload['persona'].name} commented on your post.")
        elif kind == "typing":
            self.messages.on_typing(payload)
        elif kind == "message_received":
            self.messages.on_message(payload)
            self.update_badges()
            if not self.is_viewing_chat() or self.messages.current_id != payload["conversation_id"]:
                persona = payload["persona"]
                text = payload["message"].text
                self.toast(f"{persona.name}: {text[:80]}")
                self.app.notify_message(persona.name, text, payload["conversation_id"])
            self.activity.reload()
        elif kind == "follow":
            self.toast(f"{payload.name} started following you.")
            self.activity.reload()
            self.explore.reload()
            self.profile.reload()
            self.update_badges()
            self._refresh_persona_page(payload.id)
        elif kind == "persona_created":
            self.explore.reload()
            self.toast(f"Meet {payload.name} (@{payload.handle}).")
            self.feed.reload()
            self.open_persona(payload.id)
        elif kind == "persona_updated":
            self.explore.reload()
            self.feed.reload()
            self.messages.reload()
            self._refresh_persona_page(payload.id)

    def _refresh_persona_page(self, persona_id: int) -> None:
        for page in self._pages:
            if isinstance(page, PersonaProfilePage) and page.persona_id == persona_id:
                page.reload()

    def _refresh_post_page(self, post_id: int) -> None:
        for page in self._pages:
            if isinstance(page, PostDetailPage) and page.post_id == post_id:
                page.refresh()

    def _on_close(self, *_):
        w, h = self.get_default_size()
        self.settings.set("window_width", w, save=False)
        self.settings.set("window_height", h)
        return False
