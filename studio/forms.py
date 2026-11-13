from django import forms

from .models import JournalEntry, Project, Stage


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultiplePhotoField(forms.FileField):
    """Several photos in one <input type=file multiple> (Django docs pattern).

    Files are validated as images later, by Photo.from_upload, so a bad file
    produces a clear message instead of a generic one."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"accept": "image/*", "multiple": True}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(d, initial) for d in data if d]
        return [single(data, initial)] if data else []


class QuickAddForm(forms.Form):
    """Studio form: pick a pot, tap a stage, add photos. Notes come later."""

    project = forms.ModelChoiceField(queryset=Project.objects.all(), required=False, empty_label="— New piece —")
    new_title = forms.CharField(max_length=200, required=False, label="New piece name")
    stage = forms.ChoiceField(choices=Stage.choices, widget=forms.RadioSelect)
    photos = MultiplePhotoField(required=False)
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Quick note (optional)")

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("project") and not cleaned.get("new_title", "").strip():
            self.add_error("new_title", "Pick a piece, or give the new one a name.")
        if not cleaned.get("photos") and not cleaned.get("note", "").strip():
            raise forms.ValidationError("Add at least one photo or a note.")
        return cleaned


class EntryForm(forms.ModelForm):
    """After the session: write it up, maybe add a few more photos."""

    photos = MultiplePhotoField(required=False, label="Add photos")

    class Meta:
        model = JournalEntry
        fields = ("date", "stage", "notes")
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 10, "placeholder": "What did you do? What would you change next time?"}),
        }


class GlazePhotoForm(forms.Form):
    photos = MultiplePhotoField(label="Test tiles / swatches")
    caption = forms.CharField(max_length=200, required=False, help_text="e.g. 2 coats on stoneware, cone 6")
