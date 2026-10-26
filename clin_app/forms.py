from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

from .models import User
from .panel_forms import find_user_by_phone, normalize_phone
from django import forms
from django.utils import timezone


class RegisterForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'phone', 'username')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.claim_user = None
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True

    def clean_phone(self):
        raw = self.cleaned_data.get('phone', '')
        if not raw:
            return None
        last9 = normalize_phone(raw)
        existing = find_user_by_phone(last9)
        if existing:
            # parol o'rnatilmagan bemor akkaunti = registratura yaratgan akkaunt
            claimable = existing.role == User.Role.PATIENT and not existing.has_usable_password()
            if not claimable:
                raise ValidationError("Bu telefon raqami allaqachon ro'yxatdan o'tgan.")
            self.claim_user = existing
        return f"+998{last9}"

    def clean(self):
        data = super().clean()
        if self.claim_user:
            same = (
                data.get('first_name', '').strip().lower() == self.claim_user.first_name.strip().lower()
                and data.get('last_name', '').strip().lower() == self.claim_user.last_name.strip().lower()
            )
            if not same:
                self.add_error(
                    'phone',
                    "Bu raqam registratura orqali kiritilgan. Ism va familiyani registratura "
                    "yozganidek kiriting yoki registraturaga murojaat qiling.",
                )
        return data

    def validate_unique(self):
        exclude = self._get_validation_exclusions()
        if self.claim_user:
            exclude.add('phone')
        try:
            self.instance.validate_unique(exclude=exclude)
        except ValidationError as e:
            self._update_errors(e)

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.claim_user:
            claimed = self.claim_user
            claimed.username = user.username
            claimed.first_name = user.first_name
            claimed.last_name = user.last_name
            claimed.password = user.password
            user = claimed
        user.role = User.Role.PATIENT
        if commit:
            user.save()
        return user

class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'phone', 'birth_date')
        labels = {
            'first_name': 'Ism', 'last_name': 'Familiya',
            'phone': 'Telefon', 'birth_date': "Tug'ilgan sana",
        }
        widgets = {
            'birth_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'phone': forms.TextInput(attrs={'placeholder': '+998 90 123 45 67'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['birth_date'].widget.attrs['max'] = timezone.localdate().isoformat()

    def clean_phone(self):
        raw = (self.cleaned_data.get('phone') or '').strip()
        if not raw:
            return None
        last9 = normalize_phone(raw)
        other = find_user_by_phone(last9)
        if other and other.pk != self.instance.pk:
            raise ValidationError("Bu telefon raqami boshqa akkauntga biriktirilgan.")
        return f"+998{last9}"

    def clean_birth_date(self):
        value = self.cleaned_data.get('birth_date')
        if value and (value > timezone.localdate() or value.year < 1900):
            raise ValidationError("Sana noto'g'ri.")
        return value