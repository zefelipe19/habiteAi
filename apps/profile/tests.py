from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from .models import Profile


def avatar_upload(filename):
    with BytesIO() as buffer, Image.new('RGB', (2, 2)) as image:
        image.save(buffer, format='PNG')
        return SimpleUploadedFile(filename, buffer.getvalue(), content_type='image/png')


class ProfileSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user('morador', email='morador@example.test')
        cls.other_user = User.objects.create_user('vizinho')

    def setUp(self):
        self.media_root = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(self.settings(MEDIA_ROOT=self.media_root))
        self.url = reverse('profile:settings')

    def test_profile_requires_login_and_supports_existing_accounts(self):
        login = reverse('account_login')
        self.assertRedirects(self.client.get(self.url), f'{login}?next={self.url}')
        self.assertRedirects(self.client.post(self.url, {'phone': '1234'}), f'{login}?next={self.url}')
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertContains(response, self.user.email)
        self.assertContains(response, reverse('account_email'))
        self.assertContains(response, reverse('account_change_password'))
        self.assertContains(response, f'href="{self.url}"')
        self.assertFalse(Profile.objects.exists())

    def test_saves_contact_details_only_for_the_signed_in_user(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {
            'display_name': 'Pessoa Anunciante',
            'phone': '+55 (85) 99999-0000',
            'user': self.other_user.pk,
            'email': 'outro@example.test',
        }, follow=True)

        self.assertRedirects(response, self.url)
        self.assertContains(response, 'Perfil atualizado.')
        profile = Profile.objects.get()
        self.assertEqual(profile.user, self.user)
        self.assertEqual(profile.phone, '+55 (85) 99999-0000')
        self.assertEqual(profile.display_name, 'Pessoa Anunciante')
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'morador@example.test')

    def test_rejects_invalid_avatar_without_creating_profile(self):
        self.client.force_login(self.user)
        invalid_file = SimpleUploadedFile('foto.png', b'arquivo de texto', content_type='image/png')

        response = self.client.post(self.url, {'avatar': invalid_file})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].has_error('avatar', 'invalid_image'))
        self.assertFalse(Profile.objects.exists())
        self.assertEqual(list(self.media_root.rglob('*.png')), [])

    def test_can_upload_replace_and_remove_avatar(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {'avatar': avatar_upload('perfil.png')}, follow=True)
        self.assertRedirects(response, self.url)
        profile = Profile.objects.get(user=self.user)
        first_path = self.media_root / profile.avatar.name
        self.assertTrue(first_path.is_file())
        self.assertContains(response, profile.avatar.url)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, {'avatar': avatar_upload('perfil-novo.png')})
            self.assertTrue(first_path.is_file())

        self.assertRedirects(response, self.url)
        self.assertFalse(first_path.exists())
        profile.refresh_from_db()
        second_path = self.media_root / profile.avatar.name
        self.assertTrue(second_path.is_file())

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, {'avatar-clear': 'on'})

        self.assertRedirects(response, self.url)
        profile.refresh_from_db()
        self.assertFalse(profile.avatar)
        self.assertFalse(second_path.exists())
