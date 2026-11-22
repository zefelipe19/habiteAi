from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.forms import modelform_factory
from django.test import TestCase
from PIL import Image

from .models import Property, PropertyImage


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


class PropertyImageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = get_user_model().objects.create_user(username='proprietario')
        cls.property_instance = Property.objects.create(
            title='Apartamento no Centro',
            description='Apartamento para locação.',
            property_type=Property.Type.APARTMENT,
            owner=owner,
            max_guests=2,
            bedrooms=1,
            bathrooms=1,
            beds=1,
            area_m2=Decimal('45.00'),
        )

    def setUp(self):
        self.media_root = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(self.settings(MEDIA_ROOT=self.media_root))
        self.image_form = modelform_factory(PropertyImage, fields=('property', 'image'))

    @staticmethod
    def png_upload(filename):
        with BytesIO() as buffer, Image.new('RGB', (2, 2)) as image:
            image.save(buffer, format='PNG')
            return SimpleUploadedFile(filename, buffer.getvalue(), content_type='image/png')

    def test_stores_multiple_images_for_a_property(self):
        form = self.image_form(
            data={'property': self.property_instance.pk},
            files={'image': self.png_upload('sala.png')},
        )
        self.assertTrue(form.is_valid(), form.errors)
        first = form.save()
        second = PropertyImage.objects.create(
            property=self.property_instance, image=self.png_upload('quarto.png')
        )

        self.assertCountEqual(self.property_instance.images.all(), [first, second])
        self.assertEqual(first.image.name, 'properties/images/sala.png')
        self.assertEqual(second.image.name, 'properties/images/quarto.png')
        self.assertTrue((self.media_root / first.image.name).is_file())
        self.assertTrue((self.media_root / second.image.name).is_file())

    def test_upload_form_requires_a_valid_image(self):
        invalid_image = SimpleUploadedFile('foto.png', b'arquivo de texto', content_type='image/png')
        for files, expected_error in [({}, 'required'), ({'image': invalid_image}, 'invalid_image')]:
            with self.subTest(expected_error=expected_error):
                form = self.image_form(data={'property': self.property_instance.pk}, files=files)
                self.assertFalse(form.is_valid())
                self.assertTrue(form.has_error('image', expected_error))

        self.assertFalse(self.property_instance.images.exists())

    def test_deleting_property_removes_image_record(self):
        image = PropertyImage.objects.create(
            property=self.property_instance, image=self.png_upload('sala.png')
        )

        self.property_instance.delete()

        self.assertFalse(PropertyImage.objects.filter(pk=image.pk).exists())
