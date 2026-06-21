import base64
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import PostForm
from .models import FriendRequest, Message, Post, PostComment, PostImage, PostLike, SavedPost


TEST_MEDIA_ROOT = tempfile.mkdtemp()


def video_file(name="clip.mp4", size=16):
    return SimpleUploadedFile(name, b"0" * size, content_type="video/mp4")


def image_file(name="photo.png"):
    data = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
    return SimpleUploadedFile(name, data, content_type="image/png")


def audio_file(name="sound.mp3"):
    return SimpleUploadedFile(name, b"ID3" + b"0" * 16, content_type="audio/mpeg")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class FeedTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="Pass123!")
        self.other = User.objects.create_user(username="bob", password="Pass123!")
        self.post = Post.objects.create(author=self.other, video=video_file(), description="#hello")
        self.client.force_login(self.user)

    def test_create_post_accepts_video(self):
        response = self.client.post(
            reverse("create_post"),
            {"description": "new post", "video": video_file("new.mp4")},
        )
        self.assertRedirects(response, reverse("home"))
        self.assertTrue(Post.objects.filter(author=self.user, description="new post").exists())

    def test_post_form_rejects_non_video(self):
        form = PostForm(
            data={"description": ""},
            files={"video": SimpleUploadedFile("bad.txt", b"bad", content_type="text/plain")},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("video", form.errors)

    def test_create_post_accepts_multiple_photos(self):
        response = self.client.post(
            reverse("create_post"),
            {
                "description": "photo post",
                "photos": [
                    image_file("one.png"),
                    image_file("two.png"),
                ],
            },
        )
        post = Post.objects.filter(author=self.user, description="photo post").first()
        self.assertRedirects(response, reverse("home"))
        self.assertIsNotNone(post)
        self.assertEqual(PostImage.objects.filter(post=post).count(), 2)

    def test_photo_post_accepts_audio(self):
        response = self.client.post(
            reverse("create_post"),
            {"photos": [image_file()], "audio": audio_file()},
        )
        post = Post.objects.filter(author=self.user, video__isnull=True).first()
        self.assertRedirects(response, reverse("home"))
        self.assertTrue(post.audio)

    def test_video_post_rejects_separate_audio(self):
        response = self.client.post(
            reverse("create_post"),
            {"video": video_file(), "audio": audio_file()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Свой звук можно добавить только к фотографиям")

    def test_like_and_save_ajax_actions(self):
        like_response = self.client.post(
            reverse("toggle_like", args=[self.post.id]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        save_response = self.client.post(
            reverse("toggle_save_post", args=[self.post.id]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertJSONEqual(like_response.content, {"success": True, "is_liked": True, "likes_count": 1})
        self.assertJSONEqual(save_response.content, {"success": True, "is_saved": True, "saves_count": 1})
        self.assertTrue(PostLike.objects.filter(user=self.user, post=self.post).exists())
        self.assertTrue(SavedPost.objects.filter(user=self.user, post=self.post).exists())

    def test_view_is_counted_once_per_session(self):
        url = reverse("register_view", args=[self.post.id])
        self.client.post(url)
        self.client.post(url)
        self.post.refresh_from_db()
        self.assertEqual(self.post.views, 1)

    def test_following_and_saved_feeds(self):
        FriendRequest.objects.create(from_user=self.user, to_user=self.other, status="accepted")
        SavedPost.objects.create(user=self.user, post=self.post)
        self.assertContains(self.client.get(reverse("home") + "?feed=following"), "#hello")
        self.assertContains(self.client.get(reverse("home") + "?feed=saved"), "#hello")

    def test_only_author_can_delete_post(self):
        forbidden = self.client.post(reverse("delete_post", args=[self.post.id]))
        self.assertEqual(forbidden.status_code, 404)

        own_post = Post.objects.create(author=self.user, video=video_file("own.mp4"))
        response = self.client.post(reverse("delete_post", args=[own_post.id]))
        self.assertRedirects(response, reverse("home"))
        self.assertFalse(Post.objects.filter(id=own_post.id).exists())

    def test_owner_can_manage_description_and_visibility(self):
        own_post = Post.objects.create(author=self.user, video=video_file("managed.mp4"))
        response = self.client.post(
            reverse("manage_post", args=[own_post.id]),
            {"description": "updated", "visibility": "private"},
        )
        self.assertEqual(response.status_code, 200)
        own_post.refresh_from_db()
        self.assertEqual(own_post.description, "updated")
        self.assertEqual(own_post.visibility, "private")

    def test_private_post_is_hidden_from_other_users(self):
        self.post.visibility = "private"
        self.post.save(update_fields=["visibility"])
        self.assertNotContains(self.client.get(reverse("home")), "#hello")
        self.assertEqual(self.client.post(reverse("toggle_like", args=[self.post.id])).status_code, 404)

    def test_profile_shows_public_posts_and_hides_private_posts(self):
        private_post = Post.objects.create(
            author=self.other,
            video=video_file("private-profile.mp4"),
            description="hidden profile post",
            visibility="private",
        )
        response = self.client.get(reverse("user_profile", args=[self.other.username]))
        self.assertContains(response, reverse("post_detail", args=[self.post.id]))
        self.assertNotContains(response, reverse("post_detail", args=[private_post.id]))

    def test_owner_sees_private_posts_in_profile(self):
        private_post = Post.objects.create(
            author=self.user,
            video=video_file("own-private-profile.mp4"),
            description="my private profile post",
            visibility="private",
        )
        response = self.client.get(reverse("user_profile", args=[self.user.username]))
        self.assertContains(response, reverse("post_detail", args=[private_post.id]))

    def test_search_suggestions_start_after_three_characters(self):
        short = self.client.get(reverse("search_suggestions"), {"q": "bo"})
        found = self.client.get(reverse("search_suggestions"), {"q": "bob"})
        self.assertJSONEqual(short.content, {"results": []})
        self.assertContains(found, "@bob")

    def test_search_suggestions_find_similar_phrase(self):
        response = self.client.get(reverse("search_suggestions"), {"q": "helo"})
        self.assertContains(response, "#hello")
        self.assertContains(response, "Похожая фраза")

    def test_search_suggestions_do_not_expose_profile_bio(self):
        self.other.profile.bio = "Скрытое описание профиля"
        self.other.profile.save(update_fields=["bio"])
        response = self.client.get(reverse("search_suggestions"), {"q": "bob"})
        self.assertNotContains(response, "Скрытое описание профиля")

    def test_search_suggestions_hide_private_posts(self):
        self.post.visibility = "private"
        self.post.save(update_fields=["visibility"])
        response = self.client.get(reverse("search_suggestions"), {"q": "hello"})
        self.assertNotContains(response, "#hello")

    def test_description_suggestions_find_any_user(self):
        response = self.client.get(
            reverse("description_suggestions"),
            {"kind": "mention", "q": "bo"},
        )
        self.assertContains(response, "@bob")

    def test_description_suggestions_find_existing_hashtag(self):
        response = self.client.get(
            reverse("description_suggestions"),
            {"kind": "hashtag", "q": "hell"},
        )
        self.assertContains(response, "#hello")

    def test_global_search_suggests_hashtag(self):
        response = self.client.get(reverse("search_suggestions"), {"q": "#hello"})
        self.assertContains(response, '"type": "hashtag"')
        self.assertContains(response, "#hello")

    def test_post_detail_loads_comments_with_author(self):
        response = self.client.get(reverse("post_detail", args=[self.post.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "@bob")

    def test_share_post_sends_video_to_friend_chat(self):
        FriendRequest.objects.create(from_user=self.user, to_user=self.other, status="accepted")
        response = self.client.post(
            reverse("share_post", args=[self.post.id]),
            {"recipients": [self.other.id]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Message.objects.filter(
            sender=self.user,
            receiver=self.other,
            shared_post=self.post,
        ).exists())

    def test_share_post_does_not_send_to_non_friend(self):
        response = self.client.post(
            reverse("share_post", args=[self.post.id]),
            {"recipients": [self.other.id]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Message.objects.filter(shared_post=self.post).exists())

    def test_ajax_comment_returns_avatar_field(self):
        response = self.client.post(
            reverse("add_comment", args=[self.post.id]),
            {"text": "hello"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("avatar", response.json())

    def test_comment_can_reply_to_comment_from_same_post(self):
        parent = PostComment.objects.create(post=self.post, author=self.other, text="parent")
        response = self.client.post(
            reverse("add_comment", args=[self.post.id]),
            {"text": "reply", "parent_id": parent.id},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        reply = PostComment.objects.get(text="reply")
        self.assertEqual(reply.parent, parent)
        self.assertEqual(response.json()["parent_username"], self.other.username)

    def test_comment_delete_permissions(self):
        foreign_comment = PostComment.objects.create(post=self.post, author=self.other, text="foreign")
        denied = self.client.post(reverse("delete_comment", args=[foreign_comment.id]))
        self.assertEqual(denied.status_code, 403)

        own_comment = PostComment.objects.create(post=self.post, author=self.user, text="own")
        self.client.force_login(self.other)
        allowed = self.client.post(reverse("delete_comment", args=[own_comment.id]))
        self.assertEqual(allowed.status_code, 200)
        self.assertFalse(PostComment.objects.filter(id=own_comment.id).exists())
