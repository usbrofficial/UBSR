"""Unit tests for the non-UI parts of Mirage. Run with: python3 -m unittest discover tests"""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("MIRAGE_DATA_DIR", tempfile.mkdtemp(prefix="mirage-test-"))

from mirage.ai import ChatMessage, extract_json  # noqa: E402
from mirage.art import render_post_art  # noqa: E402
from mirage.config import Settings  # noqa: E402
from mirage.db import Database  # noqa: E402
from mirage.personas import SEED_PERSONAS, normalize_persona, seed_database  # noqa: E402
from mirage import prompts  # noqa: E402


class FakeBackend:
    name = "fake"

    def __init__(self):
        self.calls = []

    def complete(self, system, messages, *, max_tokens=4096):
        self.calls.append((system, messages))
        last = messages[-1].text
        if "Return ONLY a JSON object with keys:\n  \"caption\"" in last:
            return json.dumps({"caption": "fake caption #test", "image_prompt": "a cat on a roof", "mood": "calm"})
        if "Invent one new" in last:
            return "```json\n" + json.dumps({
                "name": "Test Person", "handle": "Test.Person!", "bio": "hi", "personality": "p", "style": "s",
                "appearance": "a", "interests": ["x", "y"], "palette": ["#111111", "#222222", "#333333", "#444444"],
                "follower_count": 12, "seed_posts": ["first", "second"],
            }) + "\n```"
        if "Reply as you would in a direct message" in system:
            return "hey!\n\nhow's your day going?"
        return "nice one"


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")

    def test_profile_roundtrip(self):
        self.assertIsNone(self.db.get_profile())
        p = self.db.save_profile("Sam", "sam", "bio", None)
        self.assertEqual(p.handle, "sam")
        p2 = self.db.save_profile("Sam K", "samk", "bio2", "/tmp/x.png")
        self.assertEqual(p2.name, "Sam K")
        self.assertEqual(p2.created_at, p.created_at)

    def test_seed_and_feed(self):
        seed_database(self.db, Path(os.environ["MIRAGE_DATA_DIR"]), render_art=False)
        self.assertEqual(self.db.persona_count(), len(SEED_PERSONAS))
        feed = self.db.list_feed()
        self.assertEqual(len(feed), sum(len(p["seed_posts"]) for p in SEED_PERSONAS))
        self.assertTrue(all(feed[i].created_at >= feed[i + 1].created_at for i in range(len(feed) - 1)))
        seed_database(self.db, Path(os.environ["MIRAGE_DATA_DIR"]), render_art=False)  # idempotent
        self.assertEqual(self.db.persona_count(), len(SEED_PERSONAS))

    def test_likes_comments_and_delete(self):
        seed_database(self.db, Path("/nonexistent"), render_art=False)
        persona = self.db.list_personas()[0]
        post = self.db.add_post("me", 0, "hello", None)
        self.assertTrue(self.db.add_persona_like(post.id, persona.id))
        self.assertFalse(self.db.add_persona_like(post.id, persona.id))
        self.assertEqual(self.db.get_post(post.id).like_count, 1)
        liked = self.db.set_liked_by_me(post.id, True)
        self.assertEqual(liked.like_count, 2)
        self.assertTrue(liked.liked_by_me)
        self.db.add_comment(post.id, "persona", persona.id, "great")
        self.assertTrue(self.db.persona_commented(post.id, persona.id))
        self.assertEqual(self.db.get_post(post.id).comment_count, 1)
        self.db.delete_post(post.id)
        self.assertIsNone(self.db.get_post(post.id))
        self.assertEqual(self.db.list_comments(post.id), [])

    def test_conversations(self):
        seed_database(self.db, Path("/nonexistent"), render_art=False)
        persona = self.db.list_personas()[0]
        conv = self.db.get_or_create_conversation(persona.id)
        self.assertEqual(self.db.get_or_create_conversation(persona.id).id, conv.id)
        self.assertEqual(self.db.list_conversations(), [])  # empty conversations are hidden
        self.db.add_message(conv.id, "me", "hi")
        self.db.add_message(conv.id, "persona", "hello")
        self.assertEqual(self.db.total_unread(), 1)
        convs = self.db.list_conversations()
        self.assertEqual(len(convs), 1)
        self.assertEqual(convs[0].last_text, "hello")
        self.db.mark_conversation_read(conv.id)
        self.assertEqual(self.db.total_unread(), 0)
        self.db.delete_persona(persona.id)
        self.assertIsNone(self.db.get_persona(persona.id))
        self.assertEqual(self.db.list_messages(conv.id), [])

    def test_search(self):
        seed_database(self.db, Path("/nonexistent"), render_art=False)
        self.assertEqual([p.handle for p in self.db.list_personas("maravoss")], ["maravoss"])
        self.assertTrue(any(p.handle == "theo.lifts" for p in self.db.list_personas("strength")))


class HelperTests(unittest.TestCase):
    def test_extract_json(self):
        self.assertEqual(extract_json('Sure! {"a": 1}'), {"a": 1})
        self.assertEqual(extract_json('```json\n{"a": [1, 2]}\n```'), {"a": [1, 2]})
        self.assertEqual(extract_json('[{"x": 1}]'), [{"x": 1}])
        with self.assertRaises(ValueError):
            extract_json("no json here")

    def test_normalize_persona(self):
        taken = {"testperson"}
        data = normalize_persona({"name": "Test Person", "handle": "Test Person", "interests": "a, b"}, taken)
        self.assertEqual(data["handle"], "testperson2")
        self.assertEqual(data["interests"], ["a", "b"])
        self.assertEqual(len(data["palette"]), 4)
        self.assertGreater(data["follower_count"], 0)

    def test_render_art(self):
        out = Path(os.environ["MIRAGE_DATA_DIR"]) / "art.png"
        path = render_post_art("seed", out, ["#ff0000", "#00ff00", "#0000ff"], size=64)
        self.assertEqual(path, str(out))
        self.assertTrue(out.stat().st_size > 100)

    def test_settings(self):
        path = Path(os.environ["MIRAGE_DATA_DIR"]) / "settings.json"
        s = Settings(path)
        self.assertFalse(s.mature)
        s.set("mature_content", True, save=False)
        self.assertFalse(s.mature)  # needs age confirmation too
        s.set("age_confirmed", True)
        self.assertTrue(Settings(path).mature)

    def test_prompts_mention_policy(self):
        db = Database(":memory:")
        seed_database(db, Path("/nonexistent"), render_art=False)
        me = db.save_profile("Sam", "sam", "bio", None)
        persona = db.list_personas()[0]
        sfw = prompts.persona_system(persona, me, False)
        nsfw = prompts.persona_system(persona, me, True)
        self.assertIn("safe-for-work", sfw)
        self.assertIn("verified adult", nsfw)
        self.assertIn("under 18", nsfw)
        self.assertIn(persona.name, sfw)


class WorldTests(unittest.TestCase):
    def setUp(self):
        import gi

        gi.require_version("Gtk", "4.0")
        from mirage.simulation import World, split_bubbles

        self.split_bubbles = split_bubbles
        self.db = Database(":memory:")
        seed_database(self.db, Path("/nonexistent"), render_art=False)
        self.db.save_profile("Sam", "sam", "likes cats", None)
        self.settings = Settings(Path(os.environ["MIRAGE_DATA_DIR"]) / "s2.json")
        self.settings.set("anthropic_api_key", "test", save=False)
        self.world = World(self.db, self.settings, Path(os.environ["MIRAGE_DATA_DIR"]), time_scale=0.01)
        self.backend = FakeBackend()
        self.world._backend = self.backend
        self.world._backend_error = None
        self.world._ambient_tick = lambda: None  # keep the test deterministic
        self.events = []
        self.world.connect("event", lambda _w, kind, payload: self.events.append((kind, payload)))

    def tearDown(self):
        self.world.stop()

    def pump(self, seconds=2.0):
        from gi.repository import GLib

        ctx = GLib.MainContext.default()
        end = time.time() + seconds
        while time.time() < end:
            while ctx.pending():
                ctx.iteration(False)
            time.sleep(0.02)

    def kinds(self):
        return [k for k, _ in self.events]

    def test_split_bubbles(self):
        self.assertEqual(self.split_bubbles("a\n\nb\n\n\nc"), ["a", "b", "c"])
        self.assertEqual(self.split_bubbles("  "), [])
        self.assertEqual(len(self.split_bubbles("1\n\n2\n\n3\n\n4\n\n5\n\n6")), 4)

    def test_new_post(self):
        persona = self.db.list_personas()[0]
        self.world._do_new_post(persona.id)
        self.pump(0.3)
        self.assertIn("post_created", self.kinds())
        post = self.db.list_posts_by("persona", persona.id)[0]
        self.assertEqual(post.caption, "fake caption #test")
        self.assertEqual(post.image_prompt, "a cat on a roof")
        self.assertTrue(post.image_path and Path(post.image_path).exists())

    def test_dm_reply_flow(self):
        self.world.start()
        persona = self.db.list_personas()[1]
        conv = self.db.get_or_create_conversation(persona.id)
        self.db.add_message(conv.id, "me", "hello there")
        self.world.user_sent_dm(conv.id)
        self.pump(3.0)
        kinds = self.kinds()
        self.assertIn("typing", kinds)
        self.assertEqual(kinds.count("message_received"), 2)
        msgs = self.db.list_messages(conv.id)
        self.assertEqual([m.sender for m in msgs], ["me", "persona", "persona"])
        self.assertEqual(msgs[1].text, "hey!")
        system, history = self.backend.calls[-1]
        self.assertIn("Sam", system)
        self.assertIn("likes cats", system)
        self.assertEqual(history[-1].role, "user")
        self.assertEqual(history[-1].text, "hello there")

    def test_comment_on_my_post(self):
        post = self.db.add_post("me", 0, "my photo", None)
        persona = self.db.list_personas()[2]
        self.world._do_comment(persona.id, post.id)
        self.pump(0.3)
        self.assertIn("comment_created", self.kinds())
        self.assertEqual(self.db.list_comments(post.id)[0].text, "nice one")
        self.assertEqual(self.db.unseen_activity(), 1)
        # No duplicate comments from the same persona
        self.world._do_comment(persona.id, post.id)
        self.assertEqual(len(self.db.list_comments(post.id)), 1)

    def test_generate_persona(self):
        before = self.db.persona_count()
        self.world._do_generate_persona("someone fun")
        self.pump(0.3)
        self.assertEqual(self.db.persona_count(), before + 1)
        created = [p for k, p in self.events if k == "persona_created"][0]
        self.assertEqual(created.handle, "test.person")
        self.assertEqual(len(self.db.list_posts_by("persona", created.id)), 2)

    def test_not_configured(self):
        self.world._backend = None
        self.world._backend_error = "no key"
        self.world.user_sent_dm(1)
        self.pump(0.2)
        self.assertEqual(self.events[0], ("not_configured", "no key"))

    def test_chat_message_dataclass(self):
        m = ChatMessage("user", "hi")
        self.assertIsNone(m.image_path)


if __name__ == "__main__":
    unittest.main()
