from django.conf import settings
from django.db import models


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name='usuário',
    )
    display_name = models.CharField('nome de exibição', max_length=120, blank=True)
    phone = models.CharField('telefone', max_length=32, blank=True)
    avatar = models.ImageField(
        'foto de perfil', upload_to='profiles/avatars/', max_length=255, blank=True
    )

    class Meta:
        verbose_name = 'perfil'
        verbose_name_plural = 'perfis'

    def __str__(self):
        return self.display_name or self.user.get_username()
