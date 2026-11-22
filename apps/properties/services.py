import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from .models import Property, PropertyAddress, PropertyImage


logger = logging.getLogger(__name__)


def search_published_properties(*, q='', property_type='', guests=None):
    properties = (
        Property.objects.filter(status=Property.Status.PUBLISHED)
        .select_related('address')
        .prefetch_related('images')
        .order_by('-pk')
    )
    if q:
        properties = properties.filter(
            Q(title__icontains=q) | Q(address__city__icontains=q) | Q(address__neighborhood__icontains=q)
        )
    if property_type:
        properties = properties.filter(property_type=property_type)
    if guests is not None:
        properties = properties.filter(max_guests__gte=guests)
    return properties


def featured_property_photos():
    return (
        PropertyImage.objects.filter(property__status=Property.Status.PUBLISHED)
        .exclude(image='')
        .select_related('property')
        .order_by('-property_id', 'pk')[:5]
    )


def create_property(
    *,
    owner,
    title,
    description,
    property_type,
    max_guests,
    bedrooms,
    bathrooms,
    beds,
    area_m2,
    is_furnished=False,
    address=None,
    images=(),
    image_titles=None,
) -> Property:
    """Save a draft with its address and any uploads validated by the caller."""
    images = tuple(images)
    image_titles = ('',) * len(images) if image_titles is None else tuple(image_titles)
    if len(images) != len(image_titles):
        raise ValidationError('Os títulos informados devem corresponder às fotos selecionadas.')

    property_instance = Property(
        owner=owner,
        title=title,
        description=description,
        property_type=property_type,
        max_guests=max_guests,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        beds=beds,
        area_m2=area_m2,
        is_furnished=is_furnished,
    )
    property_instance.full_clean()
    stored_images = []
    try:
        with transaction.atomic():
            property_instance.save()
            if address is not None:
                property_address = PropertyAddress(property=property_instance, **address)
                property_address.full_clean()
                property_address.save()

            for upload, image_title in zip(images, image_titles, strict=True):
                property_image = PropertyImage(
                    property=property_instance, image=upload, title=image_title
                )
                property_image.full_clean()
                property_image.image.save(upload.name, upload, save=False)
                stored_images.append(property_image.image)
                property_image.save()
    except Exception:
        # A database rollback does not remove files already written to storage.
        for stored_image in stored_images:
            try:
                stored_image.delete(save=False)
            except Exception:
                logger.exception('Could not remove an image from a failed property creation.')
        raise

    return property_instance


def list_owner_properties(*, owner):
    return (
        Property.objects.filter(owner=owner)
        .select_related('address')
        .prefetch_related('images')
        .order_by('-pk')
    )


def update_property_status(*, owner, property_id, status):
    if status not in Property.Status.values:
        raise ValidationError({'status': 'Selecione um status válido.'})

    updated = Property.objects.filter(pk=property_id, owner=owner).update(status=status)
    if not updated:
        raise Property.DoesNotExist


def delete_property_image(*, owner, image_id):
    with transaction.atomic():
        photo = PropertyImage.objects.get(pk=image_id, property__owner=owner)
        property_id = photo.property_id
        image_file = photo.image
        photo.delete()

        def delete_unused_file():
            if image_file and not PropertyImage.objects.filter(image=image_file.name).exists():
                image_file.delete(save=False)

        transaction.on_commit(delete_unused_file, robust=True)
    return property_id
