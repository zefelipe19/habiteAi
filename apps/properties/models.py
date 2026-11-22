from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
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

    class Meta:
        verbose_name = 'imagem do imóvel'
        verbose_name_plural = 'imagens dos imóveis'

    def __str__(self):
        return str(self.image)
