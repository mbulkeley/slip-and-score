from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .images import process_photo


class Stage(models.TextChoices):
    """The life of a pot, in order. FAILED can happen at any point."""

    IDEA = "idea", "Idea"
    BUILT = "built", "Thrown / built"
    TRIMMED = "trimmed", "Trimmed"
    LEATHER_HARD = "leather_hard", "Leather-hard"
    BONE_DRY = "bone_dry", "Bone dry"
    BISQUED = "bisqued", "Bisqued"
    GLAZED = "glazed", "Glazed"
    GLAZE_FIRED = "glaze_fired", "Glaze fired"
    FINISHED = "finished", "Finished"
    FAILED = "failed", "Didn't make it"

    @classmethod
    def progression(cls):
        return [s for s in cls if s != cls.FAILED]

    @classmethod
    def after(cls, stage):
        """The usual next stage (stays put at the end, or after a failure)."""
        order = cls.progression()
        if stage not in order:
            return stage
        index = order.index(stage)
        return order[min(index + 1, len(order) - 1)]


class Method(models.TextChoices):
    WHEEL = "wheel", "Wheel thrown"
    HANDBUILT = "handbuilt", "Handbuilt"
    SLAB = "slab", "Slab"
    COIL = "coil", "Coil"
    PINCH = "pinch", "Pinch"
    OTHER = "other", "Other"


class Surface(models.TextChoices):
    GLOSS = "gloss", "Gloss"
    SATIN = "satin", "Satin"
    MATTE = "matte", "Matte"
    OTHER = "other", "Other"


class ClayBody(models.Model):
    name = models.CharField(max_length=120)
    maker = models.CharField(max_length=120, blank=True)
    cone_range = models.CharField(max_length=40, blank=True, help_text="e.g. 5–6")
    shrinkage_percent = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True, help_text="Total wet-to-fired shrinkage"
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "clay bodies"

    def __str__(self):
        return f"{self.name} ({self.maker})" if self.maker else self.name


class Glaze(models.Model):
    name = models.CharField(max_length=120)
    is_commercial = models.BooleanField(default=True, help_text="Bought ready-made (vs. mixed from a recipe)")
    maker = models.CharField(max_length=120, blank=True)
    cone_range = models.CharField(max_length=40, blank=True, help_text="e.g. 5–6")
    surface = models.CharField(max_length=10, choices=Surface.choices, blank=True)
    food_safe = models.BooleanField(null=True, blank=True, help_text="Leave unknown if not sure")
    recipe = models.TextField(blank=True, help_text="Materials and percentages, one per line")
    reference_url = models.URLField(blank=True, help_text="Maker page or Glazy.org link")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("studio:glaze_detail", args=[self.pk])

    @property
    def cover(self):
        return self.photos.first()


class Project(models.Model):
    title = models.CharField(max_length=200)
    method = models.CharField(max_length=12, choices=Method.choices, blank=True)
    clay_body = models.ForeignKey(ClayBody, null=True, blank=True, on_delete=models.SET_NULL)
    description = models.TextField(blank=True)
    is_public = models.BooleanField(
        default=False, help_text="Show in the public gallery (once there is one)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("studio:project_detail", args=[self.pk])

    @property
    def latest_entry(self):
        return self.entries.order_by("-date", "-created_at").first()

    @property
    def stage(self):
        entry = self.latest_entry
        return entry.stage if entry else Stage.IDEA

    def get_stage_display(self):
        return Stage(self.stage).label

    @property
    def next_stage(self):
        entry = self.latest_entry
        return Stage.after(entry.stage) if entry else Stage.BUILT

    @property
    def is_finished(self):
        return self.stage in (Stage.FINISHED, Stage.FAILED)

    @property
    def cover(self):
        """Most recent photo — the newest look of the piece."""
        return Photo.objects.filter(entry__project=self).order_by("-entry__date", "-created_at").first()


class JournalEntry(models.Model):
    project = models.ForeignKey(Project, related_name="entries", on_delete=models.CASCADE)
    date = models.DateField(default=timezone.localdate)
    stage = models.CharField(max_length=16, choices=Stage.choices)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name_plural = "journal entries"

    def __str__(self):
        return f"{self.project} — {self.get_stage_display()} ({self.date})"

    def get_absolute_url(self):
        return reverse("studio:entry_edit", args=[self.pk])

    @property
    def needs_notes(self):
        return not self.notes.strip()

    @classmethod
    def for_session(cls, project, stage, date=None):
        """One studio session = one entry: same project + stage + day merge."""
        date = date or timezone.localdate()
        entry, _ = cls.objects.get_or_create(project=project, stage=stage, date=date)
        return entry


def _display_path(instance, filename):
    return f"photos/{filename}"


def _thumb_path(instance, filename):
    return f"photos/thumbs/{filename}"


class Photo(models.Model):
    """A photo belongs to a journal entry or to a glaze (test tile, swatch)."""

    entry = models.ForeignKey(
        JournalEntry, null=True, blank=True, related_name="photos", on_delete=models.CASCADE
    )
    glaze = models.ForeignKey(Glaze, null=True, blank=True, related_name="photos", on_delete=models.CASCADE)
    image = models.ImageField(upload_to=_display_path, width_field="width", height_field="height")
    thumbnail = models.ImageField(upload_to=_thumb_path)
    width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    height = models.PositiveIntegerField(null=True, blank=True, editable=False)
    caption = models.CharField(max_length=200, blank=True)
    taken_at = models.DateTimeField(null=True, blank=True, help_text="From the photo's EXIF data")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["taken_at", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(entry__isnull=False, glaze__isnull=True) | Q(entry__isnull=True, glaze__isnull=False)),
                name="photo_belongs_to_entry_xor_glaze",
            )
        ]

    def __str__(self):
        return self.caption or self.image.name

    @classmethod
    def from_upload(cls, upload, **owner):
        """Process an uploaded file and save it as a Photo for `entry=` or `glaze=`."""
        return cls.from_processed(process_photo(upload), **owner)

    @classmethod
    def from_processed(cls, processed, **owner):
        """Save an already-processed photo (see images.process_photo)."""
        photo = cls(taken_at=processed.taken_at, **owner)
        photo.image.save(processed.display.name, processed.display, save=False)
        photo.thumbnail.save(processed.thumbnail.name, processed.thumbnail, save=False)
        photo.save()
        return photo

    def delete(self, *args, **kwargs):
        storage_files = [(f.storage, f.name) for f in (self.image, self.thumbnail) if f]
        result = super().delete(*args, **kwargs)
        for storage, name in storage_files:
            storage.delete(name)
        return result


class GlazeApplication(models.Model):
    class ApplyMethod(models.TextChoices):
        DIP = "dip", "Dipped"
        BRUSH = "brush", "Brushed"
        POUR = "pour", "Poured"
        SPRAY = "spray", "Sprayed"
        OTHER = "other", "Other"

    project = models.ForeignKey(Project, related_name="glaze_applications", on_delete=models.CASCADE)
    glaze = models.ForeignKey(Glaze, related_name="applications", on_delete=models.PROTECT)
    method = models.CharField(max_length=8, choices=ApplyMethod.choices, blank=True)
    coats = models.PositiveSmallIntegerField(null=True, blank=True)
    layer = models.PositiveSmallIntegerField(default=1, help_text="1 = bottom layer")
    where = models.CharField(max_length=120, blank=True, help_text="e.g. inside, rim, outside lower half")

    class Meta:
        ordering = ["layer", "pk"]

    def __str__(self):
        return f"{self.glaze} on {self.project}"
