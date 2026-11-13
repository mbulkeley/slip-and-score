from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.db import transaction
from django.db.models import Count, Prefetch
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from .forms import EntryForm, GlazePhotoForm, QuickAddForm
from .images import PhotoError, process_photo
from .models import Glaze, JournalEntry, Photo, Project, Stage


def _save_photos(request, uploads, **owner):
    """Save uploads as Photos; report unreadable files instead of failing the lot."""
    saved = 0
    for upload in uploads:
        try:
            Photo.from_upload(upload, **owner)
            saved += 1
        except PhotoError as exc:
            messages.warning(request, str(exc))
    return saved


def _entries_with_photos(queryset):
    return queryset.select_related("project").prefetch_related(
        Prefetch("photos", queryset=Photo.objects.order_by("taken_at", "created_at"))
    )


def home(request):
    needs_notes = _entries_with_photos(JournalEntry.objects.filter(notes="")).order_by("-date", "-created_at")[:20]
    recent = Project.objects.annotate(n_entries=Count("entries")).order_by("-updated_at")[:6]
    return render(request, "studio/home.html", {"needs_notes": needs_notes, "recent": recent})


def _process_uploads(request, uploads):
    """Resize every upload up front; report unreadable files and skip them."""
    processed = []
    for upload in uploads:
        try:
            processed.append(process_photo(upload))
        except PhotoError as exc:
            messages.warning(request, str(exc))
    return processed


def _shoot_day(processed):
    """The day a photo was taken (from EXIF), or today if the phone didn't say."""
    if processed.taken_at:
        return timezone.localdate(processed.taken_at)
    return timezone.localdate()


def quick_add(request):
    projects = Project.objects.order_by("-updated_at")
    if request.method == "POST":
        form = QuickAddForm(request.POST, request.FILES)
        if form.is_valid():
            data = form.cleaned_data
            # Resize first, so entries can be dated by when the photos were
            # *taken* — photos shot on Saturday and uploaded on Monday belong
            # to Saturday. A batch spanning several days becomes one entry per day.
            photos = _process_uploads(request, data["photos"])
            by_day = {}
            for photo in photos:
                by_day.setdefault(_shoot_day(photo), []).append(photo)
            note = data["note"].strip()
            if not by_day and not note:
                messages.warning(request, "None of those photos could be read, so nothing was saved.")
                return redirect("studio:quick_add")

            with transaction.atomic():
                project = data["project"] or Project.objects.create(title=data["new_title"].strip())
                days = sorted(by_day) or [timezone.localdate()]
                for day in days:
                    entry = JournalEntry.for_session(project, data["stage"], day)
                    for photo in by_day.get(day, []):
                        Photo.from_processed(photo, entry=entry)
                if note:  # the note goes with the most recent day
                    entry.notes = (entry.notes + "\n\n" + note).strip()
                    entry.save(update_fields=["notes"])
                project.save(update_fields=["updated_at"])  # bump to top of "recent"

            if photos:
                where = "" if days == [timezone.localdate()] else f" (dated {', '.join(d.strftime('%a %-d %b') for d in days)})"
                messages.success(
                    request,
                    f"Saved {len(photos)} photo{'s' if len(photos) != 1 else ''}{where} — add notes when your hands are clean.",
                )
            else:
                messages.success(request, "Saved.")
            return redirect(project)
    else:
        selected = projects.filter(pk=request.GET.get("project")).first() if request.GET.get("project") else None
        initial = {"project": selected, "stage": selected.next_stage if selected else Stage.BUILT}
        form = QuickAddForm(initial=initial)

    # For the stage auto-pick when a different piece is chosen.
    next_stages = {str(p.pk): p.next_stage for p in projects}
    return render(request, "studio/quick_add.html", {"form": form, "next_stages": next_stages})


def project_list(request):
    show = request.GET.get("show", "all")
    projects = list(Project.objects.select_related("clay_body").order_by("-updated_at"))
    if show == "active":
        projects = [p for p in projects if not p.is_finished]
    elif show == "finished":
        projects = [p for p in projects if p.is_finished]
    return render(request, "studio/project_list.html", {"projects": projects, "show": show})


def project_detail(request, pk):
    project = get_object_or_404(Project.objects.select_related("clay_body"), pk=pk)
    entries = _entries_with_photos(project.entries.all())
    applications = project.glaze_applications.select_related("glaze")
    return render(
        request,
        "studio/project_detail.html",
        {"project": project, "entries": entries, "applications": applications},
    )


def entry_edit(request, pk):
    entry = get_object_or_404(_entries_with_photos(JournalEntry.objects.all()), pk=pk)
    if request.method == "POST":
        form = EntryForm(request.POST, request.FILES, instance=entry)
        if form.is_valid():
            form.save()
            _save_photos(request, form.cleaned_data["photos"], entry=entry)
            entry.project.save(update_fields=["updated_at"])
            messages.success(request, "Notes saved.")
            return redirect(entry.project)
    else:
        form = EntryForm(instance=entry)
    return render(request, "studio/entry_edit.html", {"entry": entry, "form": form})


@require_POST
def photo_delete(request, pk):
    photo = get_object_or_404(Photo, pk=pk)
    back = photo.entry.get_absolute_url() if photo.entry_id else photo.glaze.get_absolute_url()
    photo.delete()
    messages.success(request, "Photo removed.")
    return redirect(back)


def glaze_list(request):
    glazes = Glaze.objects.annotate(n_projects=Count("applications__project", distinct=True)).prefetch_related("photos")
    return render(request, "studio/glaze_list.html", {"glazes": glazes})


def glaze_detail(request, pk):
    glaze = get_object_or_404(Glaze, pk=pk)
    if request.method == "POST":
        form = GlazePhotoForm(request.POST, request.FILES)
        if form.is_valid():
            for upload in form.cleaned_data["photos"]:
                try:
                    Photo.from_upload(upload, glaze=glaze)
                except PhotoError as exc:
                    messages.warning(request, str(exc))
            caption = form.cleaned_data["caption"]
            if caption:
                glaze.photos.filter(caption="").update(caption=caption)
            return redirect(glaze)
    else:
        form = GlazePhotoForm()
    projects = Project.objects.filter(glaze_applications__glaze=glaze).distinct()
    return render(request, "studio/glaze_detail.html", {"glaze": glaze, "form": form, "projects": projects})


@login_not_required
def manifest(request):
    """Web app manifest, so 'Add to Home Screen' opens like an app."""
    body = render_to_string("studio/manifest.webmanifest", request=request)
    return HttpResponse(body, content_type="application/manifest+json")
