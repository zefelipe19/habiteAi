from .models import Property


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
) -> Property:
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
    property_instance.save()
    return property_instance
