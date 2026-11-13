from django.contrib import admin
from django.utils.html import format_html

from .models import ClayBody, Glaze, GlazeApplication, JournalEntry, Photo, Project


def thumb(photo, size=80):
    if not photo or not photo.thumbnail:
        return "—"
    return format_html('<img src="{}" style="height:{}px;border-radius:4px">', photo.thumbnail.url, size)


class PhotoInline(admin.TabularInline):
    """Photos are added through the site (which resizes them); the admin can
    caption or remove them."""

    model = Photo
    extra = 0
    fields = ("preview", "caption", "taken_at")
    readonly_fields = ("preview", "taken_at")
    can_delete = True

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Photo")
    def preview(self, obj):
        return thumb(obj)


class GlazeApplicationInline(admin.TabularInline):
    model = GlazeApplication
    extra = 1
    autocomplete_fields = ("glaze",)


class JournalEntryInline(admin.TabularInline):
    model = JournalEntry
    extra = 0
    fields = ("date", "stage", "notes")
    show_change_link = True


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("cover_thumb", "title", "method", "clay_body", "current_stage", "is_public", "updated_at")
    list_display_links = ("cover_thumb", "title")
    list_filter = ("method", "is_public", "clay_body")
    search_fields = ("title", "description")
    inlines = (GlazeApplicationInline, JournalEntryInline)

    @admin.display(description="")
    def cover_thumb(self, obj):
        return thumb(obj.cover, 48)

    @admin.display(description="Stage")
    def current_stage(self, obj):
        return obj.get_stage_display()


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ("project", "stage", "date", "has_notes")
    list_filter = ("stage", "date")
    search_fields = ("project__title", "notes")
    date_hierarchy = "date"
    inlines = (PhotoInline,)

    @admin.display(boolean=True, description="Notes")
    def has_notes(self, obj):
        return not obj.needs_notes


@admin.register(Glaze)
class GlazeAdmin(admin.ModelAdmin):
    list_display = ("name", "maker", "cone_range", "surface", "food_safe", "is_commercial")
    list_filter = ("surface", "is_commercial", "food_safe")
    search_fields = ("name", "maker", "notes")
    inlines = (PhotoInline,)


@admin.register(ClayBody)
class ClayBodyAdmin(admin.ModelAdmin):
    list_display = ("name", "maker", "cone_range", "shrinkage_percent")
    search_fields = ("name", "maker")
