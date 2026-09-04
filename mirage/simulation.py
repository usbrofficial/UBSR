"""The world engine: makes the AI personas post, react, follow and message on their own.

All model calls run in a small thread pool. Results are written to the database
from the worker thread and announced on the GTK main loop through the ``event``
signal, so UI code never blocks and never touches threads.
"""

from __future__ import annotations

import heapq
import itertools
import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

from gi.repository import GLib, GObject

from mirage import prompts
from mirage.ai import AIError, ChatMessage, NotConfiguredError, RefusalError, extract_json, make_backend
from mirage.ai.imagegen import generate_image
from mirage.art import render_post_art
from mirage.models import Comment, Persona, Post
from mirage.personas import normalize_persona

log = logging.getLogger(__name__)

TICK_SECONDS = {"quiet": 240.0, "normal": 110.0, "busy": 45.0}


def split_bubbles(text: str, limit: int = 4) -> list[str]:
    parts = [p.strip() for p in text.replace("\r", "").split("\n\n") if p.strip()]
    if not parts:
        return []
    if len(parts) > limit:
        parts = parts[:limit - 1] + ["\n\n".join(parts[limit - 1:])]
    return parts


def typing_delay(text: str, scale: float = 1.0) -> float:
    return min(7.0, 0.9 + len(text) / 45.0) * scale


class World(GObject.Object):
    __gsignals__ = {
        # kind, payload (dict or model object)
        "event": (GObject.SignalFlags.RUN_FIRST, None, (str, object)),
    }

    def __init__(self, db, settings, media_dir: Path, time_scale: float = 1.0):
        super().__init__()
        self.db = db
        self.settings = settings
        self.media_dir = Path(media_dir)
        self.time_scale = time_scale
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mirage-ai")
        self._timers: list[tuple[float, int, Callable, tuple]] = []
        self._timer_seq = itertools.count()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._backend = None
        self._backend_error: Optional[str] = None
        self._busy = 0
        self._pending_dm: dict[int, int] = {}
        self._dm_seq = itertools.count(1)
        self._last_tick = time.time()
        self.reload_backend()

    # ------------------------------------------------------------------
    # lifecycle
    def reload_backend(self) -> None:
        try:
            self._backend = make_backend(self.settings)
            self._backend_error = None
        except NotConfiguredError as exc:
            self._backend = None
            self._backend_error = str(exc)

    @property
    def configured(self) -> bool:
        return self._backend is not None

    @property
    def configuration_problem(self) -> Optional[str]:
        return self._backend_error

    @property
    def busy(self) -> int:
        return self._busy

    def start(self) -> None:
        if self._thread:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="mirage-world", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._executor.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------
    # plumbing
    def _emit(self, kind: str, payload=None) -> None:
        def _do():
            self.emit("event", kind, payload)
            return False

        GLib.idle_add(_do)

    def _set_busy(self, delta: int) -> None:
        with self._lock:
            self._busy = max(0, self._busy + delta)
            value = self._busy
        self._emit("busy", value)

    def _submit(self, fn: Callable, *args) -> None:
        if self._stop.is_set():
            return

        def runner():
            self._set_busy(1)
            try:
                fn(*args)
            except RefusalError as exc:
                self._emit("error", f"The AI declined that one: {exc}")
            except NotConfiguredError as exc:
                self._emit("not_configured", str(exc))
            except AIError as exc:
                self._emit("error", str(exc))
            except Exception as exc:  # noqa: BLE001 - never kill the pool
                log.exception("world task failed")
                self._emit("error", f"Something went wrong: {exc}")
            finally:
                self._set_busy(-1)

        try:
            self._executor.submit(runner)
        except RuntimeError:
            pass  # executor already shut down

    def schedule(self, delay: float, fn: Callable, *args) -> None:
        when = time.time() + max(0.0, delay) * self.time_scale
        with self._lock:
            heapq.heappush(self._timers, (when, next(self._timer_seq), fn, args))

    def _loop(self) -> None:
        # First ambient tick fairly soon after launch, then at the configured cadence.
        self._last_tick = time.time() - self._tick_interval() + 25 * self.time_scale
        while not self._stop.is_set():
            now = time.time()
            due = []
            with self._lock:
                while self._timers and self._timers[0][0] <= now:
                    due.append(heapq.heappop(self._timers))
            for _, _, fn, args in due:
                self._submit(fn, *args)
            if now - self._last_tick >= self._tick_interval():
                self._last_tick = now
                try:
                    self._ambient_tick()
                except Exception:  # noqa: BLE001
                    log.exception("ambient tick failed")
            self._stop.wait(0.5)

    def _tick_interval(self) -> float:
        return TICK_SECONDS.get(self.settings.get("activity_level"), 110.0) * self.time_scale

    def _require_backend(self):
        if self._backend is None:
            raise NotConfiguredError(self._backend_error or "No AI backend configured.")
        return self._backend

    def _me(self):
        profile = self.db.get_profile()
        if profile is None:
            raise AIError("Create your profile first.")
        return profile

    def _system(self, persona: Persona, extra: str = "") -> str:
        me = self._me()
        return prompts.persona_system(
            persona, me, self.settings.mature, self.db.list_posts_by("me", 0, limit=5), extra=extra
        )

    def _random_persona(self, prefer_close: bool = True, exclude: Optional[set[int]] = None) -> Optional[Persona]:
        personas = [p for p in self.db.list_personas() if not exclude or p.id not in exclude]
        if not personas:
            return None
        if not prefer_close:
            return random.choice(personas)
        weights = [1.0 + (2.0 if p.followed else 0) + (1.5 if p.follows_me else 0) for p in personas]
        return random.choices(personas, weights=weights, k=1)[0]

    # ------------------------------------------------------------------
    # ambient behaviour
    def _ambient_tick(self) -> None:
        if not self.configured or self.db.get_profile() is None:
            return
        roll = random.random()
        my_posts = self.db.list_posts_by("me", 0, limit=6)
        if roll < 0.42:
            persona = self._random_persona()
            if persona:
                self._submit(self._do_new_post, persona.id)
        elif roll < 0.60 and my_posts:
            post = random.choice(my_posts)
            likers = set(self.db.post_likers(post.id))
            persona = self._random_persona(exclude=likers)
            if persona:
                self._submit(self._do_like, persona.id, post.id)
        elif roll < 0.74 and my_posts:
            post = random.choice(my_posts[:3])
            persona = self._random_persona()
            if persona and not self.db.persona_commented(post.id, persona.id):
                self._submit(self._do_comment, persona.id, post.id)
        elif roll < 0.86:
            self._maybe_open_dm()
        elif roll < 0.92:
            candidates = [p for p in self.db.list_personas() if not p.follows_me]
            if candidates:
                self._submit(self._do_follow_me, random.choice(candidates).id)
        else:
            feed = [p for p in self.db.list_feed(limit=20) if p.author_type == "persona"]
            if feed:
                post = random.choice(feed)
                persona = self._random_persona(prefer_close=False, exclude={post.author_id})
                if persona and not self.db.persona_commented(post.id, persona.id):
                    self._submit(self._do_comment, persona.id, post.id)

    def _maybe_open_dm(self) -> None:
        conversations = {c.persona_id: c for c in self.db.list_conversations()}
        now = time.time()
        stale = [c for c in conversations.values() if now - c.last_message_at > 3 * 3600]
        if stale and random.random() < 0.6:
            conv = random.choice(stale)
            self._submit(self._do_open_dm, conv.persona_id, "you've been thinking about your last chat and want to pick it back up")
            return
        fresh = [p for p in self.db.list_personas() if p.id not in conversations and (p.follows_me or p.followed)]
        if fresh:
            persona = random.choice(fresh)
            self._submit(self._do_open_dm, persona.id, "you've noticed their profile/posts and want to say hi")

    # ------------------------------------------------------------------
    # user-triggered hooks
    def refresh_feed(self, count: int = 3) -> None:
        if not self.configured:
            self._emit("not_configured", self._backend_error)
            return
        chosen: set[int] = set()
        for _ in range(count):
            persona = self._random_persona(exclude=chosen)
            if not persona:
                break
            chosen.add(persona.id)
            self._submit(self._do_new_post, persona.id)

    def user_posted(self, post_id: int) -> None:
        if not self.configured:
            return
        personas = self.db.list_personas()
        if not personas:
            return
        random.shuffle(personas)
        likers = personas[: random.randint(2, min(6, len(personas)))]
        for i, persona in enumerate(likers):
            self.schedule(random.uniform(8, 90) + i * 15, self._do_like, persona.id, post_id)
        commenters = personas[len(likers): len(likers) + random.randint(1, 3)]
        for i, persona in enumerate(commenters):
            self.schedule(random.uniform(20, 180) + i * 40, self._do_comment, persona.id, post_id)

    def user_commented(self, post: Post, comment: Comment) -> None:
        if not self.configured or post.author_type != "persona":
            return
        if random.random() < 0.7:
            self.schedule(random.uniform(10, 75), self._do_reply_to_comment, post.author_id, post.id, comment.id)

    def user_sent_dm(self, conversation_id: int) -> None:
        if not self.configured:
            self._emit("not_configured", self._backend_error)
            return
        seq = next(self._dm_seq)
        self._pending_dm[conversation_id] = seq
        self.schedule(random.uniform(1.0, 4.0), self._do_dm_reply, conversation_id, seq)

    def user_followed(self, persona_id: int) -> None:
        if not self.configured:
            return
        persona = self.db.get_persona(persona_id)
        if not persona:
            return
        if not persona.follows_me and random.random() < 0.55:
            self.schedule(random.uniform(20, 240), self._do_follow_me, persona_id)
        if random.random() < 0.3:
            self.schedule(random.uniform(60, 400), self._do_open_dm, persona_id, "they just followed you")

    def discover_persona(self, hint: str = "") -> None:
        if not self.configured:
            self._emit("not_configured", self._backend_error)
            return
        self._submit(self._do_generate_persona, hint)

    def ensure_avatars(self) -> None:
        if not self.settings.get("imagegen_enabled"):
            return
        missing = [p for p in self.db.list_personas() if not p.avatar_path]
        for i, persona in enumerate(missing):
            self.schedule(5 + i * 20, self._do_avatar, persona.id)

    # ------------------------------------------------------------------
    # tasks (run on worker threads)
    def _image_for(self, persona: Persona, image_prompt: str, seed: str, stem: str) -> Optional[str]:
        out = self.media_dir / f"{stem}_{int(time.time() * 1000)}.png"
        if self.settings.get("imagegen_enabled") and image_prompt:
            path = generate_image(
                self.settings.get("imagegen_url"),
                prompts.image_prompt_from(persona, image_prompt),
                out,
                steps=int(self.settings.get("imagegen_steps") or 20),
            )
            if path:
                return path
        return render_post_art(seed, out, persona.palette)

    def _do_new_post(self, persona_id: int) -> None:
        backend = self._require_backend()
        persona = self.db.get_persona(persona_id)
        if not persona:
            return
        recent = [p.caption for p in reversed(self.db.list_posts_by("persona", persona.id, limit=6))]
        instruction = prompts.new_post_instruction(
            persona, bool(self.settings.get("imagegen_enabled")), recent
        )
        raw = backend.complete(self._system(persona), [ChatMessage("user", instruction)], max_tokens=1024)
        try:
            data = extract_json(raw)
        except ValueError:
            data = {"caption": raw.strip()[:400], "image_prompt": ""}
        caption = str(data.get("caption") or "").strip()[:800]
        image_prompt = str(data.get("image_prompt") or "").strip()[:600]
        image = self._image_for(persona, image_prompt, f"{persona.handle}:{caption}", f"post_{persona.id}")
        post = self.db.add_post(
            "persona", persona.id, caption, image, image_prompt,
            like_count=random.randint(20, max(40, persona.follower_count // 40)),
        )
        self._emit("post_created", post)
        # A little chatter under the new post from other personas.
        if random.random() < 0.4:
            other = self._random_persona(prefer_close=False, exclude={persona.id})
            if other:
                self.schedule(random.uniform(30, 200), self._do_comment, other.id, post.id)

    def _do_like(self, persona_id: int, post_id: int) -> None:
        post = self.db.get_post(post_id)
        persona = self.db.get_persona(persona_id)
        if not post or not persona:
            return
        if self.db.add_persona_like(post_id, persona_id):
            if post.is_mine:
                self.db.add_activity("like", persona_id, post_id)
            self._emit("like", {"post": self.db.get_post(post_id), "persona": persona})

    def _do_comment(self, persona_id: int, post_id: int) -> None:
        backend = self._require_backend()
        post = self.db.get_post(post_id)
        persona = self.db.get_persona(persona_id)
        if not post or not persona or self.db.persona_commented(post_id, persona_id):
            return
        if post.is_mine:
            author_name = self._me().name
        else:
            author = self.db.get_persona(post.author_id)
            author_name = author.name if author else "someone"
        instruction = prompts.comment_instruction(author_name, post.caption, post.is_mine)
        image = post.image_path if (post.is_mine and post.image_path) else None
        text = backend.complete(self._system(persona), [ChatMessage("user", instruction, image)], max_tokens=512)
        text = text.strip().strip('"')
        if not text:
            return
        comment = self.db.add_comment(post_id, "persona", persona_id, text[:600])
        if post.is_mine:
            self.db.add_activity("comment", persona_id, post_id, text[:200])
        self._emit("comment_created", {"comment": comment, "post": self.db.get_post(post_id), "persona": persona})

    def _do_reply_to_comment(self, persona_id: int, post_id: int, comment_id: int) -> None:
        backend = self._require_backend()
        post = self.db.get_post(post_id)
        persona = self.db.get_persona(persona_id)
        if not post or not persona:
            return
        target = next((c for c in self.db.list_comments(post_id) if c.id == comment_id), None)
        if not target:
            return
        me = self._me()
        instruction = prompts.reply_to_comment_instruction(me.name, target.text, post.caption)
        text = backend.complete(self._system(persona), [ChatMessage("user", instruction)], max_tokens=400)
        text = text.strip().strip('"')
        if not text:
            return
        comment = self.db.add_comment(post_id, "persona", persona_id, text[:600])
        self.db.add_activity("reply", persona_id, post_id, text[:200])
        self._emit("comment_created", {"comment": comment, "post": self.db.get_post(post_id), "persona": persona})

    def _history(self, conversation_id: int, limit: int = 40) -> list[ChatMessage]:
        history = []
        for msg in self.db.list_messages(conversation_id, limit=limit):
            role = "user" if msg.sender == "me" else "assistant"
            history.append(ChatMessage(role, msg.text or "(photo)", msg.image_path if role == "user" else None))
        return history

    def _deliver(self, conversation_id: int, persona: Persona, text: str, kind: str = "reply") -> None:
        bubbles = split_bubbles(text)
        if not bubbles:
            return
        self._emit("typing", {"conversation_id": conversation_id, "typing": True, "persona": persona})
        self.schedule(typing_delay(bubbles[0]), self._store_message, conversation_id, persona.id, bubbles, kind)

    def _store_message(self, conversation_id: int, persona_id: int, bubbles: list[str], kind: str) -> None:
        """Store the next bubble, then chain the following one so they always arrive in order."""
        text, rest = bubbles[0], bubbles[1:]
        message = self.db.add_message(conversation_id, "persona", text)
        persona = self.db.get_persona(persona_id)
        if not rest:
            self._emit("typing", {"conversation_id": conversation_id, "typing": False, "persona": persona})
            if kind == "opener":
                self.db.add_activity("message", persona_id, None, text[:200])
        self._emit("message_received", {"message": message, "persona": persona, "conversation_id": conversation_id})
        if rest:
            self.schedule(typing_delay(rest[0]), self._store_message, conversation_id, persona_id, rest, kind)
        else:
            count = len(self.db.list_messages(conversation_id, limit=1000))
            if count % 12 == 0:
                self.schedule(2, self._do_update_notes, conversation_id)

    def _do_dm_reply(self, conversation_id: int, seq: int) -> None:
        if self._pending_dm.get(conversation_id) != seq:
            return  # superseded by a newer message from the user
        backend = self._require_backend()
        conv = self.db.get_conversation(conversation_id)
        if not conv:
            return
        persona = self.db.get_persona(conv.persona_id)
        if not persona:
            return
        history = self._history(conversation_id)
        if not history or history[-1].role != "user":
            return
        self._emit("typing", {"conversation_id": conversation_id, "typing": True, "persona": persona})
        try:
            text = backend.complete(
                self._system(persona, prompts.dm_reply_instruction()), history, max_tokens=1024
            )
        except AIError:
            self._emit("typing", {"conversation_id": conversation_id, "typing": False, "persona": persona})
            raise
        if self._pending_dm.get(conversation_id) != seq:
            self._emit("typing", {"conversation_id": conversation_id, "typing": False, "persona": persona})
            return
        self._pending_dm.pop(conversation_id, None)
        self._deliver(conversation_id, persona, text)

    def _do_open_dm(self, persona_id: int, reason: str) -> None:
        backend = self._require_backend()
        persona = self.db.get_persona(persona_id)
        if not persona:
            return
        conv = self.db.get_or_create_conversation(persona_id)
        if self._pending_dm.get(conv.id):
            return
        history = self._history(conv.id, limit=20)
        if history and history[-1].role == "user":
            # They're waiting on us already; answer instead of opening anew.
            self.user_sent_dm(conv.id)
            return
        text = backend.complete(
            self._system(persona, prompts.dm_opener_instruction(reason)),
            history + [ChatMessage("user", "(You decide to send them a message now.)")],
            max_tokens=600,
        )
        self._deliver(conv.id, persona, text, kind="opener")

    def _do_update_notes(self, conversation_id: int) -> None:
        backend = self._require_backend()
        conv = self.db.get_conversation(conversation_id)
        if not conv:
            return
        persona = self.db.get_persona(conv.persona_id)
        if not persona:
            return
        me = self._me()
        lines = []
        for msg in self.db.list_messages(conversation_id, limit=30):
            who = me.name if msg.sender == "me" else persona.name
            lines.append(f"{who}: {msg.text}")
        instruction = prompts.memory_update_instruction(persona, me, "\n".join(lines), persona.notes)
        notes = backend.complete(
            "You write concise private memory notes. Return only the notes.",
            [ChatMessage("user", instruction)], max_tokens=400,
        )
        if notes.strip():
            self.db.update_persona_notes(persona.id, notes.strip())

    def _do_follow_me(self, persona_id: int) -> None:
        persona = self.db.get_persona(persona_id)
        if not persona or persona.follows_me:
            return
        self.db.set_follows_me(persona_id, True)
        self.db.add_activity("follow", persona_id)
        self._emit("follow", self.db.get_persona(persona_id))

    def _do_generate_persona(self, hint: str) -> None:
        backend = self._require_backend()
        me = self.db.get_profile()
        instruction = prompts.persona_generation_prompt(self.db.all_handles(), hint, self.settings.mature, me)
        raw = backend.complete(
            "You invent believable fictional people for a social-network simulation. Return only JSON.",
            [ChatMessage("user", instruction)], max_tokens=1500,
        )
        data = extract_json(raw)
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            raise AIError("The model didn't return a usable profile. Try again.")
        taken = set(self.db.all_handles())
        clean = normalize_persona(data, taken, index=len(taken))
        seed_posts = clean.pop("seed_posts", [])
        persona = self.db.add_persona(clean)
        now = time.time()
        for j, caption in enumerate(seed_posts):
            image = render_post_art(f"{persona.handle}:{caption}", self.media_dir / f"post_{persona.id}_seed{j}.png",
                                    persona.palette)
            self.db.add_post("persona", persona.id, caption, image, "",
                             like_count=random.randint(30, 900), created_at=now - (j + 1) * random.uniform(4, 40) * 3600)
        self._emit("persona_created", persona)
        if self.settings.get("imagegen_enabled"):
            self.schedule(2, self._do_avatar, persona.id)

    def _do_avatar(self, persona_id: int) -> None:
        persona = self.db.get_persona(persona_id)
        if not persona or persona.avatar_path or not self.settings.get("imagegen_enabled"):
            return
        out = self.media_dir / f"avatar_{persona.id}.png"
        path = generate_image(
            self.settings.get("imagegen_url"), prompts.avatar_prompt(persona), out,
            steps=int(self.settings.get("imagegen_steps") or 20), width=512, height=512,
        )
        if path:
            self.db.set_persona_avatar(persona_id, path)
            self._emit("persona_updated", self.db.get_persona(persona_id))
