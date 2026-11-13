import shutil
import tempfile
from datetime import date
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from .images import PhotoError, process_photo
from .models import Glaze, GlazeApplication, JournalEntry, Photo, Project, Stage

MEDIA = tempfile.mkdtemp()


def jpeg(name="pot.jpg", size=(3000, 2000), exif_date=None, orientation=None):
    image = Image.new("RGB", size, "#b5603a")
    exif = Image.Exif()
    if exif_date:
        exif.get_ifd(0x8769)[36867] = exif_date
    if orientation:
        exif[0x0112] = orientation
    buffer = BytesIO()
    image.save(buffer, "JPEG", exif=exif)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


@override_settings(MEDIA_ROOT=MEDIA)
class BaseTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.user = get_user_model().objects.create_user("potter", password="test-password-not-real")
        self.client.force_login(self.user)


class StageTests(TestCase):
    def test_after_follows_progression(self):
        self.assertEqual(Stage.after(Stage.BUILT), Stage.TRIMMED)
        self.assertEqual(Stage.after(Stage.GLAZED), Stage.GLAZE_FIRED)

    def test_after_stays_at_end_and_after_failure(self):
        self.assertEqual(Stage.after(Stage.FINISHED), Stage.FINISHED)
        self.assertEqual(Stage.after(Stage.FAILED), Stage.FAILED)


class ImageTests(TestCase):
    def test_resizes_and_names_with_uuid(self):
        processed = process_photo(jpeg())
        self.assertRegex(processed.display.name, r"^[0-9a-f]{32}\.jpg$")
        with Image.open(processed.display) as display:
            self.assertEqual(max(display.size), 2000)
        with Image.open(processed.thumbnail) as thumb:
            self.assertEqual(max(thumb.size), 480)

    def test_reads_shoot_time_then_strips_exif(self):
        processed = process_photo(jpeg(exif_date="2026:11:13 10:15:00"))
        self.assertEqual(processed.taken_at.date(), date(2026, 11, 13))
        self.assertEqual(processed.taken_at.hour, 10)
        with Image.open(processed.display) as display:
            self.assertEqual(len(display.getexif()), 0)  # GPS etc. gone

    def test_applies_rotation(self):
        # Orientation 6 = rotate 90° CW: a landscape sensor image becomes portrait.
        processed = process_photo(jpeg(size=(400, 300), orientation=6))
        self.assertEqual((processed.width, processed.height), (300, 400))

    def test_rejects_non_images(self):
        with self.assertRaises(PhotoError):
            process_photo(SimpleUploadedFile("notes.txt", b"not an image"))


class AuthTests(TestCase):
    def test_pages_require_login(self):
        for name in ("studio:home", "studio:quick_add", "studio:project_list", "studio:glaze_list"):
            response = self.client.get(reverse(name))
            self.assertRedirects(response, f"{reverse('login')}?next={reverse(name)}", msg_prefix=name)

    def test_manifest_is_public(self):
        response = self.client.get(reverse("studio:manifest"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/manifest+json")


class QuickAddTests(BaseTest):
    def test_new_piece_with_photos(self):
        response = self.client.post(
            reverse("studio:quick_add"),
            {"project": "", "new_title": "Tall blue vase", "stage": Stage.BUILT, "photos": [jpeg("a.jpg"), jpeg("b.jpg")]},
        )
        project = Project.objects.get(title="Tall blue vase")
        self.assertRedirects(response, project.get_absolute_url())
        entry = project.entries.get()
        self.assertEqual(entry.stage, Stage.BUILT)
        self.assertEqual(entry.photos.count(), 2)
        self.assertTrue(entry.needs_notes)

    def test_same_session_merges_into_one_entry(self):
        project = Project.objects.create(title="Mug")
        for name in ("1.jpg", "2.jpg"):
            self.client.post(reverse("studio:quick_add"), {"project": project.pk, "stage": Stage.TRIMMED, "photos": [jpeg(name)]})
        self.assertEqual(project.entries.count(), 1)
        self.assertEqual(project.entries.get().photos.count(), 2)

    def test_needs_photo_or_note(self):
        project = Project.objects.create(title="Bowl")
        response = self.client.post(reverse("studio:quick_add"), {"project": project.pk, "stage": Stage.BUILT})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(project.entries.exists())

    def test_bad_file_is_reported_good_ones_kept(self):
        project = Project.objects.create(title="Plate")
        bad = SimpleUploadedFile("x.heic", b"garbage", content_type="image/heic")
        response = self.client.post(
            reverse("studio:quick_add"), {"project": project.pk, "stage": Stage.BUILT, "photos": [jpeg(), bad]}, follow=True
        )
        self.assertEqual(Photo.objects.count(), 1)
        self.assertContains(response, "Couldn&#x27;t read x.heic")

    def test_entries_dated_by_shoot_day(self):
        project = Project.objects.create(title="Platter")
        self.client.post(
            reverse("studio:quick_add"),
            {
                "project": project.pk,
                "stage": Stage.BUILT,
                "photos": [
                    jpeg("sat1.jpg", exif_date="2026:11:07 10:00:00"),
                    jpeg("sat2.jpg", exif_date="2026:11:07 11:30:00"),
                    jpeg("sun.jpg", exif_date="2026:11:08 09:00:00"),
                ],
                "note": "Uploaded on Monday.",
            },
        )
        entries = {e.date: e for e in project.entries.all()}
        self.assertEqual(sorted(entries), [date(2026, 11, 7), date(2026, 11, 8)])
        self.assertEqual(entries[date(2026, 11, 7)].photos.count(), 2)
        self.assertEqual(entries[date(2026, 11, 8)].photos.count(), 1)
        self.assertEqual(entries[date(2026, 11, 8)].notes, "Uploaded on Monday.")

    def test_photo_without_exif_date_goes_to_today(self):
        project = Project.objects.create(title="Spoon rest")
        self.client.post(reverse("studio:quick_add"), {"project": project.pk, "stage": Stage.BUILT, "photos": [jpeg()]})
        self.assertEqual(project.entries.get().date, timezone.localdate())

    def test_all_photos_unreadable_saves_nothing(self):
        project = Project.objects.create(title="Tile")
        bad = SimpleUploadedFile("x.heic", b"garbage", content_type="image/heic")
        self.client.post(reverse("studio:quick_add"), {"project": project.pk, "stage": Stage.BUILT, "photos": [bad]})
        self.assertFalse(project.entries.exists())

    def test_defaults_to_next_stage(self):
        project = Project.objects.create(title="Jar")
        JournalEntry.objects.create(project=project, stage=Stage.BISQUED)
        response = self.client.get(reverse("studio:quick_add") + f"?project={project.pk}")
        self.assertEqual(response.context["form"].initial["stage"], Stage.GLAZED)


class NotesFlowTests(BaseTest):
    def test_home_lists_entries_without_notes_until_written(self):
        project = Project.objects.create(title="Teapot")
        entry = JournalEntry.objects.create(project=project, stage=Stage.BUILT)
        self.assertEqual(list(self.client.get(reverse("studio:home")).context["needs_notes"]), [entry])

        response = self.client.post(
            reverse("studio:entry_edit", args=[entry.pk]),
            {"date": entry.date.isoformat(), "stage": Stage.BUILT, "notes": "Spout pulled off-centre."},
        )
        self.assertRedirects(response, project.get_absolute_url())
        entry.refresh_from_db()
        self.assertFalse(entry.needs_notes)
        self.assertEqual(list(self.client.get(reverse("studio:home")).context["needs_notes"]), [])

    def test_photo_delete_removes_files(self):
        project = Project.objects.create(title="Cup")
        entry = JournalEntry.objects.create(project=project, stage=Stage.BUILT)
        photo = Photo.from_upload(jpeg(), entry=entry)
        storage, names = photo.image.storage, (photo.image.name, photo.thumbnail.name)
        self.client.post(reverse("studio:photo_delete", args=[photo.pk]))
        self.assertFalse(Photo.objects.exists())
        self.assertFalse(any(storage.exists(n) for n in names))


class GlazeTests(BaseTest):
    def test_glaze_page_shows_pieces_and_takes_test_tiles(self):
        glaze = Glaze.objects.create(name="Floating Blue", maker="Amaco", cone_range="5–6")
        project = Project.objects.create(title="Serving bowl")
        GlazeApplication.objects.create(project=project, glaze=glaze, coats=3)

        response = self.client.get(glaze.get_absolute_url())
        self.assertContains(response, "Serving bowl")

        self.client.post(glaze.get_absolute_url(), {"photos": [jpeg()], "caption": "3 coats, cone 6"})
        self.assertEqual(glaze.photos.get().caption, "3 coats, cone 6")


class PageSmokeTests(BaseTest):
    def test_all_pages_render(self):
        glaze = Glaze.objects.create(name="Shino")
        project = Project.objects.create(title="Vase")
        entry = JournalEntry.objects.create(project=project, stage=Stage.GLAZED, notes="Dipped twice.")
        Photo.from_upload(jpeg(), entry=entry)
        GlazeApplication.objects.create(project=project, glaze=glaze)
        urls = [
            reverse("studio:home"),
            reverse("studio:quick_add"),
            reverse("studio:project_list"),
            reverse("studio:project_list") + "?show=active",
            reverse("studio:project_list") + "?show=finished",
            project.get_absolute_url(),
            entry.get_absolute_url(),
            reverse("studio:glaze_list"),
            glaze.get_absolute_url(),
            reverse("admin:studio_project_changelist"),
            reverse("admin:studio_project_change", args=[project.pk]),
            reverse("admin:studio_journalentry_change", args=[entry.pk]),
            reverse("admin:studio_glaze_change", args=[glaze.pk]),
        ]
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


class LightboxTests(BaseTest):
    def test_photo_links_open_in_viewer_not_bare_image(self):
        """In the home-screen app there's no back button, so photo links must
        be handled by the in-page viewer (data-lightbox), not navigate away."""
        glaze = Glaze.objects.create(name="Celadon")
        project = Project.objects.create(title="Bowl")
        entry = JournalEntry.objects.create(project=project, stage=Stage.BUILT)
        Photo.from_upload(jpeg(), entry=entry)
        Photo.from_upload(jpeg(), glaze=glaze)
        for url, group in (
            (project.get_absolute_url(), f"entry-{entry.pk}"),
            (entry.get_absolute_url(), f"entry-{entry.pk}"),
            (glaze.get_absolute_url(), f"glaze-{glaze.pk}"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, f'data-lightbox="{group}"')
                self.assertContains(response, "studio/lightbox.js")
