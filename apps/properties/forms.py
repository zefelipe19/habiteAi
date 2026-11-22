from django import forms

from .models import Property


class PropertyForm(forms.ModelForm):
    class Meta:
        model = Property
        fields = (
            'title',
            'description',
            'property_type',
            'max_guests',
            'bedrooms',
            'bathrooms',
            'beds',
            'area_m2',
            'is_furnished',
        )
        localized_fields = ('area_m2',)
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'area_m2': forms.TextInput(attrs={'inputmode': 'decimal'}),
            'is_furnished': forms.CheckboxInput(attrs={'class': 'check'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')
