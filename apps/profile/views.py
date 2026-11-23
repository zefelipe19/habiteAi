from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import ProfileForm
from .services import get_user_profile, update_user_profile


@login_required
@require_http_methods(['GET', 'HEAD', 'POST'])
def profile_settings(request):
    profile = get_user_profile(user=request.user)
    current_avatar = profile.avatar
    is_post = request.method == 'POST'
    form = ProfileForm(
        request.POST if is_post else None,
        request.FILES if is_post else None,
        instance=profile,
    )
    if is_post and form.is_valid():
        try:
            update_user_profile(
                user=request.user,
                display_name=form.cleaned_data['display_name'],
                phone=form.cleaned_data['phone'],
                avatar=form.cleaned_data['avatar'] if 'avatar' in form.changed_data else None,
            )
        except ValidationError as error:
            form.add_error(None, error.messages)
        except OSError:
            form.add_error('avatar', 'Não foi possível salvar a foto. Tente novamente.')
        else:
            messages.success(request, 'Perfil atualizado.')
            return redirect('profile:settings')

    return render(request, 'profile/settings.html', {'current_avatar': current_avatar, 'form': form})
