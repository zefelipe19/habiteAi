from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from .models import Property


class PropertyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(
            username='proprietario', email='proprietario@example.test'
        )
        cls.property_data = {
            'title': 'Studio no Centro',
            'description': 'Imóvel disponível para locação mensal ou por temporada.',
            'property_type': Property.Type.STUDIO,
            'owner': cls.owner,
            'max_guests': 2,
            'bedrooms': 0,
            'bathrooms': 1,
            'beds': 0,
            'area_m2': Decimal('32.50'),
        }

    def test_creates_unfurnished_draft_linked_to_owner(self):
        property_instance = Property(**self.property_data)
        property_instance.full_clean()
        property_instance.save()

        saved_property = self.owner.properties.get(pk=property_instance.pk)
        self.assertEqual(saved_property.status, Property.Status.DRAFT)
        self.assertFalse(saved_property.is_furnished)
        self.assertEqual(saved_property.area_m2, Decimal('32.50'))
        self.assertEqual(saved_property.bedrooms, 0)
        self.assertEqual(saved_property.beds, 0)
        self.assertEqual(str(saved_property), 'Studio no Centro')

    def test_validates_counts_area_and_choices(self):
        invalid_fields = {
            'max_guests': 0,
            'bedrooms': -1,
            'bathrooms': -1,
            'beds': -1,
            'area_m2': Decimal('0.00'),
            'property_type': 'invalid',
            'status': 'invalid',
        }
        for field, value in invalid_fields.items():
            with self.subTest(field=field):
                property_instance = Property(**{**self.property_data, field: value})
                with self.assertRaises(ValidationError) as error:
                    property_instance.full_clean()
                self.assertIn(field, error.exception.message_dict)

    def test_database_rejects_zero_capacity_and_area(self):
        for field, value in [('max_guests', 0), ('area_m2', Decimal('0.00'))]:
            with self.subTest(field=field):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Property.objects.create(**{**self.property_data, field: value})

    def test_prevents_deleting_owner_of_existing_property(self):
        property_instance = Property.objects.create(**self.property_data)

        with self.assertRaises(ProtectedError):
            self.owner.delete()

        self.assertTrue(self.owner.properties.filter(pk=property_instance.pk).exists())
