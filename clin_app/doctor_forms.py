from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import TimeOff


class TimeOffForm(forms.ModelForm):
    class Meta:
        model = TimeOff
        fields = ("start_date", "end_date", "reason")
        labels = {"start_date": "Boshlanish sanasi", "end_date": "Tugash sanasi", "reason": "Sabab (ixtiyoriy)"}
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "reason": forms.TextInput(attrs={"placeholder": "Masalan: ta'til"}),
        }

    def clean(self):
        data = super().clean()
        start, end = data.get("start_date"), data.get("end_date")
        if start and end:
            if end < start:
                raise ValidationError("Tugash sanasi boshlanishdan oldin bo'lishi mumkin emas.")
            if end < timezone.localdate():
                raise ValidationError("O'tib ketgan sanalarni kiritib bo'lmaydi.")
        return data