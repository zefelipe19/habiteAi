from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.forms import modelform_factory
from django.test import Client, TestCase
from django.urls import reverse
from PIL import Image

from .models import Property, PropertyAddress, PropertyImage
from .services import create_property


def png_upload(filename):
    with BytesIO() as buffer, Image.new('RGB', (2, 2)) as image:
        image.save(buffer, format='PNG')
        return SimpleUploadedFile(filename, buffer.getvalue(), content_type='image/png')


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
        self.image_form = modelform_factory(PropertyImage, fields=('property', 'image', 'title'))

    def test_stores_multiple_images_for_a_property(self):
        form = self.image_form(
            data={'property': self.property_instance.pk},
            files={'image': png_upload('sala.png')},
        )
        self.assertTrue(form.is_valid(), form.errors)
        first = form.save()
        second = PropertyImage.objects.create(
            property=self.property_instance, image=png_upload('quarto.png')
        )

        self.assertCountEqual(self.property_instance.images.all(), [first, second])
        self.assertEqual(first.image.name, 'properties/images/sala.png')
        self.assertEqual(second.image.name, 'properties/images/quarto.png')
        self.assertTrue((self.media_root / first.image.name).is_file())
        self.assertTrue((self.media_root / second.image.name).is_file())
        self.assertEqual(first.title, '')
        self.assertEqual(second.title, '')

    def test_saves_optional_room_title(self):
        form = self.image_form(
            data={'property': self.property_instance.pk, 'title': 'Sala de estar'},
            files={'image': png_upload('sala.png')},
        )

        self.assertTrue(form.is_valid(), form.errors)
        photo = form.save()
        photo.refresh_from_db()
        self.assertEqual(photo.title, 'Sala de estar')
        self.assertEqual(str(photo), 'Sala de estar')

    def test_image_title_rejects_more_than_100_characters(self):
        form = self.image_form(
            data={'property': self.property_instance.pk, 'title': 'x' * 101},
            files={'image': png_upload('sala.png')},
        )

        self.assertFalse(form.is_valid())
        self.assertTrue(form.has_error('title', 'max_length'))

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
            property=self.property_instance, image=png_upload('sala.png')
        )

        self.property_instance.delete()

        self.assertFalse(PropertyImage.objects.filter(pk=image.pk).exists())


class PropertyAddressTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = get_user_model().objects.create_user(username='proprietario')
        cls.property_instance = Property.objects.create(
            title='Apartamento',
            description='Imóvel para locação.',
            property_type=Property.Type.APARTMENT,
            owner=owner,
            max_guests=2,
            bedrooms=1,
            bathrooms=1,
            beds=1,
            area_m2=Decimal('45.00'),
        )
        cls.address_data = {
            'property': cls.property_instance,
            'street': 'Rua Exemplo',
            'number': '12A',
            'city': 'São Paulo',
            'state': 'SP',
            'postal_code': '01000-000',
        }

    def test_saves_address_before_and_after_geocoding(self):
        address = PropertyAddress(**self.address_data)
        address.full_clean()
        address.save()
        self.assertEqual(self.property_instance.address.pk, address.pk)
        self.assertEqual(address.country_code, 'BR')
        self.assertEqual(address.postal_code, '01000-000')
        self.assertIsNone(address.latitude)
        self.assertIsNone(address.longitude)

        address.latitude = Decimal('0.000000')
        address.longitude = Decimal('-40.123456')
        address.full_clean()
        address.save(update_fields=['latitude', 'longitude'])
        address.refresh_from_db()
        self.assertEqual(address.latitude, Decimal('0.000000'))
        self.assertEqual(address.longitude, Decimal('-40.123456'))

    def test_rejects_partial_and_out_of_range_coordinates(self):
        for latitude, longitude in [
            (0, None),
            (None, 0),
            (Decimal('-90.000001'), 0),
            (0, Decimal('180.000001')),
        ]:
            with self.subTest(latitude=latitude, longitude=longitude):
                address = PropertyAddress(**self.address_data, latitude=latitude, longitude=longitude)
                with self.assertRaises(ValidationError):
                    address.full_clean()
                with self.assertRaises(IntegrityError), transaction.atomic():
                    address.save()

    def test_rejects_second_address_for_same_property(self):
        PropertyAddress.objects.create(**self.address_data)

        with self.assertRaises(IntegrityError), transaction.atomic():
            PropertyAddress.objects.create(**self.address_data)


class PropertyCreationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username='proprietario')
        cls.other_user = User.objects.create_user(username='outro')
        cls.property_data = {
            'title': 'Apartamento no Centro',
            'description': 'Imóvel para locação.',
            'property_type': Property.Type.APARTMENT,
            'max_guests': 2,
            'bedrooms': 1,
            'bathrooms': 1,
            'beds': 1,
            'area_m2': Decimal('45.50'),
            'is_furnished': True,
        }
        cls.address_data = {
            'address-postal_code': '01000-000',
            'address-street': 'Rua Exemplo',
            'address-number': '12A',
            'address-city': 'São Paulo',
            'address-state': 'SP',
            'address-country_code': 'br',
        }

    def setUp(self):
        self.media_root = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(self.settings(MEDIA_ROOT=self.media_root))

    def test_creation_requires_login(self):
        url = reverse('property_create')
        login_url = reverse('account_login')

        self.assertRedirects(self.client.get(url), f'{login_url}?next={url}')
        self.assertRedirects(self.client.post(url, self.property_data), f'{login_url}?next={url}')
        self.assertFalse(Property.objects.exists())

    def test_logged_in_user_can_create_own_draft(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        url = reverse('property_create')
        self.assertContains(client.get(reverse('index')), f'href="{url}">Anunciar imóvel')
        self.assertContains(client.get(url), 'name="csrfmiddlewaretoken"')

        response = client.post(
            url,
            {
                **self.property_data,
                **self.address_data,
                'area_m2': '45,50',
                'address-latitude': '-23,550520',
                'address-longitude': '-46,633308',
                'images': [png_upload('sala.png'), png_upload('quarto.png')],
                'image_titles': [' Sala de estar ', ''],
                'owner': self.other_user.pk,
                'status': Property.Status.PUBLISHED,
                'csrfmiddlewaretoken': client.cookies['csrftoken'].value,
            },
            follow=True,
        )

        self.assertRedirects(response, url)
        self.assertContains(response, 'Imóvel cadastrado como rascunho.')
        property_instance = Property.objects.get()
        self.assertEqual(property_instance.owner, self.owner)
        self.assertEqual(property_instance.status, Property.Status.DRAFT)
        self.assertEqual(property_instance.area_m2, Decimal('45.50'))
        self.assertTrue(property_instance.is_furnished)
        self.assertEqual(property_instance.address.postal_code, '01000-000')
        self.assertEqual(property_instance.address.country_code, 'BR')
        self.assertIsNone(property_instance.address.latitude)
        self.assertIsNone(property_instance.address.longitude)
        image_titles = dict(property_instance.images.values_list('image', 'title'))
        self.assertEqual(image_titles, {
            'properties/images/sala.png': 'Sala de estar',
            'properties/images/quarto.png': '',
        })
        self.assertTrue(all((self.media_root / name).is_file() for name in image_titles))

    def test_view_shows_errors_without_saving_invalid_property(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('property_create'),
            {**self.property_data, **self.address_data, 'max_guests': 0},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].has_error('max_guests', 'min_value'))
        self.assertFalse(Property.objects.exists())

    def test_can_save_draft_with_address_without_photos(self):
        self.client.force_login(self.owner)
        url = reverse('property_create')

        response = self.client.post(url, {**self.property_data, **self.address_data})

        self.assertRedirects(response, url)
        property_instance = Property.objects.get()
        self.assertEqual(property_instance.address.street, 'Rua Exemplo')
        self.assertIsNone(property_instance.address.latitude)
        self.assertFalse(property_instance.images.exists())

    def test_rejects_incomplete_address_without_saving_uploaded_file(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('property_create'),
            {
                **self.property_data,
                **self.address_data,
                'address-city': '',
                'images': [png_upload('sala.png')],
            },
        )

        self.assertTrue(response.context['address_form'].has_error('city', 'required'))
        self.assertContains(response, 'Selecione as fotos novamente antes de salvar.')
        self.assertFalse(Property.objects.exists())
        self.assertEqual(list(self.media_root.rglob('*.png')), [])

    def test_address_step_does_not_render_coordinates(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('property_create'))

        self.assertContains(response, 'name="address-street"')
        self.assertNotContains(response, 'name="address-latitude"')
        self.assertNotContains(response, 'name="address-longitude"')

    def test_rejects_all_uploads_if_one_image_is_invalid(self):
        self.client.force_login(self.owner)
        invalid = SimpleUploadedFile('invalida.png', b'arquivo de texto', content_type='image/png')
        response = self.client.post(
            reverse('property_create'),
            {**self.property_data, **self.address_data, 'images': [png_upload('sala.png'), invalid]},
        )

        self.assertTrue(response.context['images_form'].has_error('images', 'invalid_image'))
        self.assertContains(response, 'value="Rua Exemplo"')
        self.assertFalse(Property.objects.exists())
        self.assertEqual(list(self.media_root.rglob('*.png')), [])

    def test_rejects_invalid_titles_without_saving_any_images(self):
        self.client.force_login(self.owner)
        for titles, expected_error in [
            (['x' * 101, 'Quarto'], 'max_length'),
            (['Sala'], 'image_titles_mismatch'),
        ]:
            with self.subTest(expected_error=expected_error):
                response = self.client.post(
                    reverse('property_create'),
                    {
                        **self.property_data,
                        **self.address_data,
                        'images': [png_upload('sala.png'), png_upload('quarto.png')],
                        'image_titles': titles,
                    },
                )

                self.assertTrue(response.context['images_form'].has_error('images', expected_error))
                self.assertFalse(Property.objects.exists())
                self.assertEqual(list(self.media_root.rglob('*.png')), [])

    def test_failed_storage_rolls_back_draft_and_cleans_up_previous_uploads(self):
        self.client.force_login(self.owner)
        storage = PropertyImage._meta.get_field('image').storage
        save_file = storage.save

        def save_first_file_only(name, content, **kwargs):
            if name.endswith('quarto.png'):
                raise OSError('Falha simulada no armazenamento')
            return save_file(name, content, **kwargs)

        with patch.object(storage, 'save', side_effect=save_first_file_only):
            response = self.client.post(
                reverse('property_create'),
                {
                    **self.property_data,
                    **self.address_data,
                    'images': [png_upload('sala.png'), png_upload('quarto.png')],
                },
            )

        self.assertContains(response, 'Não foi possível salvar as fotos.')
        self.assertFalse(Property.objects.exists())
        self.assertFalse(PropertyAddress.objects.exists())
        self.assertFalse(PropertyImage.objects.exists())
        self.assertEqual(list(self.media_root.rglob('*.png')), [])

    def test_service_validates_input_without_an_http_request(self):
        with self.assertRaises(ValidationError) as error:
            create_property(owner=self.owner, **{**self.property_data, 'max_guests': 0})

        self.assertIn('max_guests', error.exception.message_dict)
        self.assertFalse(Property.objects.exists())


class PropertyManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username='dono')
        cls.other_user = User.objects.create_user(username='vizinho')
        shared_data = {
            'description': 'Imóvel para locação.',
            'property_type': Property.Type.APARTMENT,
            'max_guests': 2,
            'bedrooms': 1,
            'bathrooms': 1,
            'beds': 1,
            'area_m2': Decimal('45.50'),
        }
        cls.own_property = Property.objects.create(title='Meu apartamento', owner=cls.owner, **shared_data)
        cls.other_property = Property.objects.create(title='Apartamento vizinho', owner=cls.other_user, **shared_data)

    def setUp(self):
        self.media_root = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(self.settings(MEDIA_ROOT=self.media_root))
        self.photo = PropertyImage.objects.create(
            property=self.own_property, image=png_upload('sala.png'), title='Sala de estar'
        )
        self.other_photo = PropertyImage.objects.create(property=self.other_property, image=png_upload('quarto.png'))

    def test_owner_list_uses_home_cards_and_links_to_management(self):
        gallery_url = reverse('my_properties')
        self.assertRedirects(self.client.get(gallery_url), f'{reverse("account_login")}?next={gallery_url}')
        self.client.force_login(self.owner)

        response = self.client.get(gallery_url)

        self.assertTemplateUsed(response, 'properties/_property_card.html')
        self.assertContains(response, self.own_property.title)
        self.assertContains(response, self.photo.image.url)
        self.assertContains(response, reverse('property_manage', args=[self.own_property.pk]))
        self.assertNotContains(response, 'name="status"')
        self.assertNotContains(response, 'Remover foto')
        self.assertNotContains(response, self.other_property.title)
        self.assertNotContains(response, self.other_photo.image.url)

    def test_management_shows_own_status_and_gallery(self):
        self.client.force_login(self.owner)
        url = reverse('property_manage', args=[self.own_property.pk])

        response = self.client.get(url)

        self.assertEqual(response.context['status_form']['status'].value(), Property.Status.DRAFT)
        self.assertContains(response, '<p class="property-photo-title">Sala de estar</p>', html=True)
        self.assertContains(response, 'data-photo-viewer')
        self.assertContains(response, reverse('property_edit', args=[self.own_property.pk]))
        self.assertContains(response, f'name="removed_images" value="{self.photo.pk}"')
        self.assertNotContains(response, self.other_photo.image.url)

    def edit_data(self, **changes):
        return {
            **{name: getattr(self.own_property, name) for name in Property.INFORMATION_FIELDS},
            **changes,
        }

    def test_edits_information_and_photos_together(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        manage_url = reverse('property_manage', args=[self.own_property.pk])
        url = reverse('property_edit', args=[self.own_property.pk])
        client.get(manage_url)
        old_file = self.media_root / self.photo.image.name

        with self.captureOnCommitCallbacks(execute=True):
            response = client.post(url, self.edit_data(
                title='Meu apartamento atualizado',
                description='Descrição atualizada.',
                max_guests=4,
                bedrooms=2,
                area_m2='65,20',
                images=[png_upload('varanda.png')],
                image_titles=['Varanda'],
                removed_images=[self.photo.pk],
                status=Property.Status.PUBLISHED,
                owner=self.other_user.pk,
                csrfmiddlewaretoken=client.cookies['csrftoken'].value,
                edited_fields='title,description,max_guests,bedrooms,area_m2,status,owner',
            ))
            self.assertTrue(old_file.exists())

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['redirect'], manage_url)
        self.own_property.refresh_from_db()
        self.assertEqual(self.own_property.title, 'Meu apartamento atualizado')
        self.assertEqual(self.own_property.description, 'Descrição atualizada.')
        self.assertEqual(self.own_property.max_guests, 4)
        self.assertEqual(self.own_property.bedrooms, 2)
        self.assertEqual(self.own_property.area_m2, Decimal('65.20'))
        self.assertEqual(self.own_property.status, Property.Status.DRAFT)
        self.assertEqual(self.own_property.owner, self.owner)
        photo = self.own_property.images.get()
        self.assertEqual(photo.title, 'Varanda')
        self.assertTrue((self.media_root / photo.image.name).is_file())
        self.assertFalse(old_file.exists())

    def test_editor_keeps_fields_changed_elsewhere_when_only_photos_are_edited(self):
        self.client.force_login(self.owner)
        data = self.edit_data(images=[png_upload('varanda.png')], edited_fields='')
        Property.objects.filter(pk=self.own_property.pk).update(title='Título atualizado em outra aba')

        response = self.client.post(reverse('property_edit', args=[self.own_property.pk]), data)

        self.assertEqual(response.status_code, 200, response.content)
        self.own_property.refresh_from_db()
        self.assertEqual(self.own_property.title, 'Título atualizado em outra aba')
        self.assertEqual(self.own_property.images.count(), 2)

    def test_editor_rejects_editing_or_removing_images_from_another_property(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse('property_edit', args=[self.other_property.pk]), self.edit_data())
        self.assertEqual(response.status_code, 404)

        response = self.client.post(
            reverse('property_edit', args=[self.own_property.pk]),
            self.edit_data(title='Tentativa', removed_images=[self.other_photo.pk]),
        )

        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json()['errors'])
        self.own_property.refresh_from_db()
        self.assertEqual(self.own_property.title, 'Meu apartamento')
        self.assertTrue(PropertyImage.objects.filter(pk=self.other_photo.pk).exists())

    def test_failed_edited_upload_rolls_back_fields_and_staged_removal(self):
        self.client.force_login(self.owner)
        storage = PropertyImage._meta.get_field('image').storage
        save_file = storage.save

        def save_first_file_only(name, content, **kwargs):
            if name.endswith('falha.png'):
                raise OSError('Falha simulada no armazenamento')
            return save_file(name, content, **kwargs)

        with patch.object(storage, 'save', side_effect=save_first_file_only):
            response = self.client.post(
                reverse('property_edit', args=[self.own_property.pk]),
                self.edit_data(
                    title='Tentativa', removed_images=[self.photo.pk],
                    images=[png_upload('nova.png'), png_upload('falha.png')],
                ),
            )

        self.assertEqual(response.status_code, 503)
        self.own_property.refresh_from_db()
        self.assertEqual(self.own_property.title, 'Meu apartamento')
        self.assertEqual(list(self.own_property.images.all()), [self.photo])
        self.assertTrue((self.media_root / self.photo.image.name).is_file())
        self.assertFalse((self.media_root / 'properties/images/nova.png').exists())

    def test_owner_can_publish_and_hide_property_from_home(self):
        self.client.force_login(self.owner)
        url = reverse('property_manage', args=[self.own_property.pk])
        home = reverse('index')
        headers = {'HX-Request': 'true'}

        self.assertNotContains(self.client.get(home, headers=headers), self.own_property.title)
        for status, is_public in [(Property.Status.PUBLISHED, True), (Property.Status.INACTIVE, False)]:
            with self.subTest(status=status):
                response = self.client.post(url, {'status': status, 'owner': self.other_user.pk}, follow=True)
                self.assertRedirects(response, url)
                self.assertContains(response, 'Disponibilidade atualizada.')
                self.own_property.refresh_from_db()
                self.assertEqual(self.own_property.status, status)
                self.assertEqual(self.own_property.owner, self.owner)
                results = self.client.get(home, headers=headers)
                self.assertEqual(self.own_property.title in results.content.decode(), is_public)

    def test_management_rejects_other_owners_and_invalid_status(self):
        url = reverse('property_manage', args=[self.own_property.pk])
        self.assertRedirects(self.client.get(url), f'{reverse("account_login")}?next={url}')
        self.client.force_login(self.other_user)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {'status': Property.Status.PUBLISHED}).status_code, 404)

        self.client.force_login(self.owner)
        response = self.client.post(url, {'status': 'unknown'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['status_form'].has_error('status', 'invalid_choice'))
        self.own_property.refresh_from_db()
        self.assertEqual(self.own_property.status, Property.Status.DRAFT)

    def test_only_owner_can_delete_through_csrf_protected_post(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        manage_url = reverse('property_manage', args=[self.own_property.pk])
        own_url = reverse('property_image_delete', args=[self.photo.pk])
        other_url = reverse('property_image_delete', args=[self.other_photo.pk])

        self.assertEqual(client.get(own_url).status_code, 405)
        self.assertEqual(client.post(own_url).status_code, 403)
        client.get(manage_url)
        csrf = {'csrfmiddlewaretoken': client.cookies['csrftoken'].value}
        self.assertEqual(client.post(other_url, csrf).status_code, 404)

        file_path = self.media_root / self.photo.image.name
        with self.captureOnCommitCallbacks(execute=True):
            response = client.post(own_url, csrf, follow=True)
            self.assertTrue(file_path.is_file())

        self.assertRedirects(response, manage_url)
        self.assertContains(response, 'Foto removida do imóvel.')
        self.assertFalse(PropertyImage.objects.filter(pk=self.photo.pk).exists())
        self.assertTrue(PropertyImage.objects.filter(pk=self.other_photo.pk).exists())
        self.assertFalse(file_path.exists())
        self.assertTrue((self.media_root / self.other_photo.image.name).is_file())

    def test_removing_photo_preserves_file_referenced_by_another_record(self):
        other_reference = PropertyImage.objects.create(
            property=self.other_property, image=self.photo.image.name
        )
        self.client.force_login(self.owner)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('property_image_delete', args=[self.photo.pk]))

        self.assertRedirects(response, reverse('property_manage', args=[self.own_property.pk]))
        self.assertTrue((self.media_root / other_reference.image.name).is_file())


class HomeSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = get_user_model().objects.create_user(username='anunciante')
        shared_fields = {
            'description': 'Imóvel para locação.',
            'owner': owner,
            'bedrooms': 1,
            'bathrooms': 1,
            'beds': 1,
            'area_m2': Decimal('45.00'),
        }
        cls.house = Property.objects.create(
            title='Casa com varanda', property_type=Property.Type.HOUSE,
            status=Property.Status.PUBLISHED, max_guests=4, **shared_fields,
        )
        cls.studio = Property.objects.create(
            title='Studio no Centro', property_type=Property.Type.STUDIO,
            status=Property.Status.PUBLISHED, max_guests=2, **shared_fields,
        )
        cls.draft = Property.objects.create(
            title='Rascunho privado', property_type=Property.Type.HOUSE,
            status=Property.Status.DRAFT, max_guests=4, **shared_fields,
        )
        for property_instance in (cls.house, cls.studio, cls.draft):
            PropertyAddress.objects.create(
                property=property_instance, street='Rua Exemplo', number='12',
                neighborhood='Centro', city='Fortaleza', state='CE', postal_code='60000-000',
            )
        PropertyImage.objects.create(property=cls.house, image='properties/images/varanda.png')
        PropertyImage.objects.create(property=cls.studio, image='properties/images/studio.png')
        PropertyImage.objects.create(property=cls.draft, image='properties/images/privada.png')

    def test_home_shows_search_gallery_footer_and_only_published_properties(self):
        response = self.client.get(reverse('index'))

        self.assertContains(response, 'id="home-search"')
        self.assertContains(response, 'hx-target="#property-results"')
        self.assertContains(response, 'class="site-footer"')
        self.assertContains(response, 'properties/images/varanda.png')
        self.assertContains(response, 'properties/images/studio.png')
        self.assertContains(response, 'x-data="homeCarousel"')
        self.assertContains(response, reverse('property_detail', args=[self.house.pk]))
        self.assertNotContains(response, 'Rascunho privado')
        self.assertNotContains(response, 'properties/images/privada.png')

    def test_public_detail_shows_photos_and_only_city_state_and_neighborhood(self):
        address = self.house.address
        address.street = 'Rua do endereço privado'
        address.number = '123Q'
        address.complement = 'Unidade interna'
        address.latitude = Decimal('-23.550520')
        address.longitude = Decimal('-46.633308')
        address.save()

        response = self.client.get(reverse('property_detail', args=[self.house.pk]))

        self.assertContains(response, '<h1>Casa com varanda</h1>', html=True)
        self.assertContains(response, '<dt>Cidade</dt><dd>Fortaleza</dd>')
        self.assertContains(response, '<dt>Estado</dt><dd>CE</dd>')
        self.assertContains(response, '<dt>Bairro</dt><dd>Centro</dd>')
        self.assertContains(response, 'properties/images/varanda.png')
        self.assertContains(response, 'data-photo-viewer')
        for private_value in (
            address.street, address.number, address.complement, address.postal_code,
            str(address.latitude), str(address.longitude),
        ):
            with self.subTest(value=private_value):
                self.assertNotContains(response, private_value)

    def test_public_detail_shows_property_characteristics_and_description(self):
        self.house.description = 'Casa com jardim.\n\nSala <ampla> e ventilada.'
        self.house.bedrooms = 0
        self.house.bathrooms = 2
        self.house.beds = 3
        self.house.area_m2 = Decimal('45.50')
        self.house.is_furnished = True
        self.house.save()

        response = self.client.get(reverse('property_detail', args=[self.house.pk]))

        self.assertContains(response, '<h2 id="information-title">Sobre o imóvel</h2>', html=True)
        for label, value in [
            ('Tipo de imóvel', 'Casa'), ('Capacidade', '4 hóspedes'), ('Quartos', '0'),
            ('Banheiros', '2'), ('Camas', '3'), ('Área', '45,50 m²'), ('Mobília', 'Mobiliado'),
        ]:
            with self.subTest(label=label):
                self.assertContains(response, f'<dt>{label}</dt><dd>{value}</dd>')
        self.assertContains(response, '<p>Casa com jardim.</p>', html=True)
        self.assertContains(response, '<p>Sala &lt;ampla&gt; e ventilada.</p>')

    def test_public_detail_is_unavailable_for_draft_or_inactive_property(self):
        self.studio.status = Property.Status.INACTIVE
        self.studio.save(update_fields=['status'])
        for property_instance in (self.draft, self.studio):
            with self.subTest(status=property_instance.status):
                response = self.client.get(reverse('property_detail', args=[property_instance.pk]))
                self.assertEqual(response.status_code, 404)

    def test_public_detail_handles_legacy_property_without_address_or_photos(self):
        self.house.address.delete()
        self.house.images.all().delete()

        response = self.client.get(reverse('property_detail', args=[self.house.pk]))

        self.assertContains(response, 'Localização ainda não informada.')
        self.assertContains(response, 'Este imóvel está sem fotos.')
        self.assertNotContains(response, 'data-photo-viewer')

    def test_search_combines_location_type_and_capacity_for_htmx(self):
        response = self.client.get(
            reverse('index'), {'q': 'Fortaleza', 'property_type': 'house', 'guests': 4},
            headers={'HX-Request': 'true'},
        )

        self.assertContains(response, 'id="property-results"')
        self.assertContains(response, 'Casa com varanda')
        self.assertNotContains(response, 'Studio no Centro')
        self.assertNotContains(response, 'Rascunho privado')
        self.assertNotContains(response, 'id="home-search"')
        self.assertIn('HX-Request', response['Vary'])

    def test_search_without_htmx_and_history_restore_render_full_page(self):
        headers_to_test = (
            {},
            {'HX-Request': 'true', 'HX-History-Restore-Request': 'true'},
        )
        for headers in headers_to_test:
            with self.subTest(headers=headers):
                response = self.client.get(
                    reverse('index'), {'q': 'Centro', 'guests': 3}, headers=headers,
                )
                self.assertContains(response, 'id="home-search"')
                self.assertEqual(list(response.context['page_obj']), [self.house])

    def test_invalid_and_unmatched_filters_have_distinct_messages(self):
        invalid = self.client.get(reverse('index'), {'guests': 0}, headers={'HX-Request': 'true'})
        self.assertContains(invalid, 'Confira os filtros')
        self.assertNotContains(invalid, 'Casa com varanda')

        unmatched = self.client.get(reverse('index'), {'q': 'Recife'}, headers={'HX-Request': 'true'})
        self.assertContains(unmatched, 'Nenhum imóvel encontrado')
        self.assertNotContains(unmatched, 'Casa com varanda')

    def test_pagination_preserves_filters(self):
        Property.objects.bulk_create([
            Property(
                title=f'Casa {number}', description='Imóvel para locação.', owner=self.house.owner,
                property_type=Property.Type.HOUSE, status=Property.Status.PUBLISHED, max_guests=4,
                bedrooms=1, bathrooms=1, beds=1, area_m2=Decimal('45.00'),
            )
            for number in range(12)
        ])
        filters = {'property_type': 'house', 'guests': 4}
        response = self.client.get(reverse('index'), filters, headers={'HX-Request': 'true'})
        self.assertContains(response, '?property_type=house&amp;guests=4&amp;page=2#imoveis')
        self.assertEqual(len(response.context['page_obj']), 12)

        second_page = self.client.get(reverse('index'), {**filters, 'page': 2}, headers={'HX-Request': 'true'})
        self.assertEqual(list(second_page.context['page_obj']), [self.house])
