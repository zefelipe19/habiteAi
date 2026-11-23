from django import forms

from .models import Profile


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ('display_name', 'phone', 'avatar')
        widgets = {
            'display_name': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'nickname'}),
            'phone': forms.TextInput(attrs={
                'class': 'form-control', 'type': 'tel', 'autocomplete': 'tel',
            }),
            'avatar': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }
