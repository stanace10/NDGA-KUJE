from django import forms
from core.upload_scan import validate_json_upload


class SyncDashboardFilterForm(forms.Form):
    operation_type = forms.ChoiceField(
        required=False,
        choices=(("", "All operations"),),
    )
    status = forms.ChoiceField(
        required=False,
        choices=(("", "All statuses"),),
    )

    def __init__(self, *args, operation_choices=None, status_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        if operation_choices:
            self.fields["operation_type"].choices = (("", "All operations"),) + tuple(
                operation_choices
            )
        if status_choices:
            self.fields["status"].choices = (("", "All statuses"),) + tuple(status_choices)
        self.fields["operation_type"].widget.attrs.update(
            {"class": "w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm"}
        )
        self.fields["status"].widget.attrs.update(
            {"class": "w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm"}
        )


class SyncImportForm(forms.Form):
    snapshot_file = forms.FileField(required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["snapshot_file"].widget.attrs.update(
            {"class": "w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm"}
        )

    def clean_snapshot_file(self):
        upload = self.cleaned_data["snapshot_file"]
        return validate_json_upload(upload)
