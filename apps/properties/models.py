from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models


class Property(models.Model):
    class Type(models.TextChoices):
        HOUSE = 'house', 'Casa'
        APARTMENT = 'apartment', 'Apartamento'
        STUDIO = 'studio', 'Studio'
        ROOM = 'room', 'Quarto'
        CHALET = 'chalet', 'Chalé'
        COUNTRY_HOUSE = 'country_house', 'Sítio ou chácara'
        OTHER = 'other', 'Outro'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Rascunho'
        PUBLISHED = 'published', 'Publicado'
        INACTIVE = 'inactive', 'Inativo'

    title = models.CharField('título', max_length=200)
    description = models.TextField('descrição')
    property_type = models.CharField('tipo de imóvel', max_length=20, choices=Type.choices)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='properties',
        verbose_name='proprietário',
    )
    max_guests = models.PositiveSmallIntegerField(
        'capacidade máxima', validators=[MinValueValidator(1)]
    )
    bedrooms = models.PositiveSmallIntegerField('quartos')
    bathrooms = models.PositiveSmallIntegerField('banheiros')
    beds = models.PositiveSmallIntegerField('camas')
    area_m2 = models.DecimalField(
        'área em m²',
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    is_furnished = models.BooleanField('mobiliado', default=False)
    status = models.CharField(
        'status', max_length=12, choices=Status.choices, default=Status.DRAFT
    )

    class Meta:
        verbose_name = 'imóvel'
        verbose_name_plural = 'imóveis'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(max_guests__gte=1),
                name='property_max_guests_at_least_one',
            ),
            models.CheckConstraint(
                condition=models.Q(area_m2__gt=0),
                name='property_area_m2_positive',
            ),
        ]

    def __str__(self):
        return self.title


class PropertyImage(models.Model):
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='images',
        verbose_name='imóvel',
    )
    image = models.ImageField('imagem', upload_to='properties/images/', max_length=255)
    title = models.CharField('título', max_length=100, blank=True, default='')

    class Meta:
        verbose_name = 'imagem do imóvel'
        verbose_name_plural = 'imagens dos imóveis'

    def __str__(self):
        return self.title or str(self.image)


class PropertyAddress(models.Model):
    property = models.OneToOneField(
        Property,
        on_delete=models.CASCADE,
        related_name='address',
        verbose_name='imóvel',
    )
    street = models.CharField('logradouro', max_length=200)
    number = models.CharField('número', max_length=20)
    complement = models.CharField('complemento', max_length=120, blank=True)
    neighborhood = models.CharField('bairro', max_length=100, blank=True)
    city = models.CharField('cidade', max_length=100)
    state = models.CharField('estado ou província', max_length=100)
    postal_code = models.CharField('CEP ou código postal', max_length=20)
    country_code = models.CharField(
        'código do país',
        max_length=2,
        default='BR',
        validators=[
            RegexValidator(r'\A[A-Z]{2}\Z', 'Use duas letras maiúsculas para o código do país.'),
        ],
    )
    latitude = models.DecimalField(
        'latitude',
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        'longitude',
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )

    class Meta:
        verbose_name = 'endereço do imóvel'
        verbose_name_plural = 'endereços dos imóveis'
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(latitude__isnull=True, longitude__isnull=True)
                    | models.Q(
                        latitude__isnull=False,
                        longitude__isnull=False,
                        latitude__range=(-90, 90),
                        longitude__range=(-180, 180),
                    )
                ),
                name='property_address_valid_coordinates',
                violation_error_message='Informe latitude e longitude juntas e dentro dos limites válidos.',
            ),
        ]

    def __str__(self):
        locality = f'{self.city} - {self.state}'
        return f'{self.street}, {self.number}, {locality}, {self.postal_code}, {self.country_code}'
