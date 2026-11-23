import logging

from django.db import transaction

from .models import Profile


logger = logging.getLogger(__name__)


def get_user_profile(*, user):
    return Profile.objects.filter(user=user).first() or Profile(user=user)


def _delete_unused_avatar(avatar):
    if not Profile.objects.filter(avatar=avatar.name).exists():
        avatar.delete(save=False)


def update_user_profile(*, user, display_name, phone, avatar=None):
    """Update the contact details. False clears the avatar and None leaves it alone."""
    stored_avatar = None
    try:
        with transaction.atomic():
            profile, _ = Profile.objects.select_for_update().get_or_create(user=user)
            previous_avatar = profile.avatar
            profile.display_name = display_name
            profile.phone = phone
            fields_to_save = ['display_name', 'phone']

            if avatar is not None:
                profile.avatar = '' if avatar is False else avatar
                fields_to_save.append('avatar')

            profile.full_clean()
            if avatar is not None and avatar is not False:
                profile.avatar.save(avatar.name, avatar, save=False)
                stored_avatar = profile.avatar
            profile.save(update_fields=fields_to_save)

            if previous_avatar and previous_avatar.name != profile.avatar.name:
                transaction.on_commit(lambda: _delete_unused_avatar(previous_avatar), robust=True)
    except Exception:
        # A database rollback does not remove an uploaded file from storage.
        if stored_avatar:
            try:
                stored_avatar.delete(save=False)
            except Exception:
                logger.exception('Could not remove an avatar from a failed profile update.')
        raise

    return profile
