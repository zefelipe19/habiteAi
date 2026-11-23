from django import forms
from django.core.exceptions import ValidationError

from .models import Property, PropertyAddress, PropertyImage


class PropertySearchForm(forms.Form):
    q = forms.CharField(
        label='Local ou imóvel',
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={'type': 'search', 'placeholder': 'Cidade, bairro ou nome'}),
    )
    property_type = forms.ChoiceField(
        label='Tipo de imóvel',
        choices=[('', 'Todos os tipos'), *Property.Type.choices],
        required=False,
    )
    guests = forms.IntegerField(label='Hóspedes', min_value=1, max_value=32767, required=False)


class PropertyStatusForm(forms.Form):
    status = forms.ChoiceField(
        label='Status do anúncio',
        choices=[
            (Property.Status.DRAFT, 'Rascunho'),
            (Property.Status.PUBLISHED, 'Publicado (disponível)'),
            (Property.Status.INACTIVE, 'Inativo (indisponível)'),
        ],
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text='Os imóveis publicados aparecem na busca da página inicial.',
    )


class BootstrapModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')


class PropertyForm(BootstrapModelForm):
    max_guests = forms.IntegerField(label='Capacidade máxima', min_value=1)

    class Meta:
        model = Property
        fields = Property.INFORMATION_FIELDS
        localized_fields = ('area_m2',)
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'area_m2': forms.TextInput(attrs={'inputmode': 'decimal'}),
            'is_furnished': forms.CheckboxInput(attrs={'class': 'check'}),
        }


class PropertyAddressForm(BootstrapModelForm):
    class Meta:
        model = PropertyAddress
        fields = (
            'postal_code',
            'street',
            'number',
            'complement',
            'neighborhood',
            'city',
            'state',
            'country_code',
        )
        widgets = {
            'postal_code': forms.TextInput(attrs={'autocomplete': 'postal-code'}),
            'street': forms.TextInput(attrs={'autocomplete': 'address-line1'}),
            'complement': forms.TextInput(attrs={'autocomplete': 'address-line2'}),
            'neighborhood': forms.TextInput(attrs={'autocomplete': 'address-level3'}),
            'city': forms.TextInput(attrs={'autocomplete': 'address-level2'}),
            'state': forms.TextInput(attrs={'autocomplete': 'address-level1'}),
            'country_code': forms.TextInput(attrs={'autocomplete': 'country'}),
        }

    def clean_country_code(self):
        return self.cleaned_data['country_code'].upper()


class MultipleImageInput(forms.FileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    widget = MultipleImageInput(attrs={'class': 'form-control', 'accept': 'image/*'})

    def clean(self, data, initial=None):
        clean_image = super().clean
        if not data:
            return clean_image(None, initial) or []
        uploads = data if isinstance(data, (list, tuple)) else [data]
        return [clean_image(upload) for upload in uploads]


class PropertyImagesForm(forms.Form):
    title_max_length = PropertyImage._meta.get_field('title').max_length

    images = MultipleImageField(
        label='Fotos do imóvel (opcional)',
        required=False,
        help_text='Você pode selecionar várias fotos de uma vez.',
    )

    def __init__(self, *args, image_titles=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.image_titles = image_titles

    def clean(self):
        cleaned_data = super().clean()
        if 'images' not in cleaned_data or not self.image_titles:
            return cleaned_data

        if len(self.image_titles) != len(cleaned_data['images']):
            self.add_error('images', ValidationError(
                'Selecione as fotos novamente para associar os títulos.',
                code='image_titles_mismatch',
            ))
            return cleaned_data

        title_field = forms.CharField(required=False, max_length=self.title_max_length)
        try:
            cleaned_data['image_titles'] = [title_field.clean(title) for title in self.image_titles]
        except ValidationError as error:
            self.add_error('images', error)
        return cleaned_data


class PropertyImageEditForm(PropertyImagesForm):
    removed_images = forms.ModelMultipleChoiceField(
        queryset=PropertyImage.objects.none(),
        label='Fotos para remover',
        required=False,
    )

    def __init__(self, *args, property_instance, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['removed_images'].queryset = PropertyImage.objects.filter(property=property_instance)
