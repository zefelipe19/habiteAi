from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST, require_safe
from django.views.decorators.vary import vary_on_headers

from .forms import (
    PropertyAddressForm,
    PropertyForm,
    PropertyImageEditForm,
    PropertyImagesForm,
    PropertySearchForm,
    PropertyStatusForm,
)
from .models import Property, PropertyImage
from .services import (
    create_property,
    delete_property_image,
    featured_property_photos,
    list_owner_properties,
    search_published_properties,
    update_property,
    update_property_status,
)


@require_safe
@vary_on_headers('HX-Request', 'HX-History-Restore-Request')
def index(request):
    search_form = PropertySearchForm(request.GET)
    filters_are_valid = search_form.is_valid()
    properties = (
        search_published_properties(**search_form.cleaned_data)
        if filters_are_valid else Property.objects.none()
    )
    context = {
        'search_form': search_form,
        'has_filters': any(search_form.cleaned_data.values()),
        'page_obj': Paginator(properties, 12).get_page(request.GET.get('page')),
        'page_title': 'HabiteAi | Imóveis para alugar',
        'page_description': 'Encontre imóveis para alugar por temporada ou por mês no HabiteAi.',
    }
    if request.headers.get('HX-Request') == 'true' and request.headers.get('HX-History-Restore-Request') != 'true':
        return render(request, 'properties/_search_results.html', context)

    context['featured_photos'] = list(featured_property_photos())
    return render(request, 'index.html', context)


@require_safe
def property_detail(request, property_id):
    property_instance = get_object_or_404(search_published_properties(), pk=property_id)
    return render(request, 'properties/property_detail.html', {
        'property': property_instance,
        'photos': [photo for photo in property_instance.images.all() if photo.image],
        'page_title': f'{property_instance.title} | HabiteAi',
    })


@login_required
@require_http_methods(['GET', 'HEAD', 'POST'])
def property_create(request):
    data = request.POST if request.method == 'POST' else None
    form = PropertyForm(data)
    address_form = PropertyAddressForm(data, prefix='address')
    images_form = PropertyImagesForm(
        data,
        request.FILES if data is not None else None,
        image_titles=data.getlist('image_titles') if data is not None else (),
    )

    if data is not None and all([form.is_valid(), address_form.is_valid(), images_form.is_valid()]):
        try:
            create_property(
                owner=request.user,
                address=address_form.cleaned_data,
                images=images_form.cleaned_data['images'],
                image_titles=images_form.cleaned_data.get('image_titles'),
                **form.cleaned_data,
            )
        except ValidationError as error:
            form.add_error(None, error.messages)
        except OSError:
            images_form.add_error('images', 'Não foi possível salvar as fotos. Tente novamente.')
        else:
            messages.success(request, 'Imóvel cadastrado como rascunho.')
            return redirect('property_create')

    return render(request, 'properties/property_form.html', {
        'form': form,
        'address_form': address_form,
        'images_form': images_form,
        'reselect_images': bool(request.FILES),
    })


@login_required
@require_safe
def my_properties(request):
    properties = list_owner_properties(owner=request.user)
    return render(request, 'properties/my_properties.html', {'properties': properties})


@login_required
@require_http_methods(['GET', 'HEAD', 'POST'])
def property_manage(request, property_id):
    property_instance = get_object_or_404(list_owner_properties(owner=request.user), pk=property_id)
    status_form = PropertyStatusForm(
        request.POST if request.method == 'POST' else None,
        initial={'status': property_instance.status},
    )
    if request.method == 'POST' and status_form.is_valid():
        try:
            update_property_status(
                owner=request.user, property_id=property_id, status=status_form.cleaned_data['status']
            )
        except Property.DoesNotExist as error:
            raise Http404 from error
        messages.success(request, 'Disponibilidade atualizada.')
        return redirect('property_manage', property_id=property_id)

    return render(request, 'properties/property_manage.html', {
        'property': property_instance,
        'status_form': status_form,
        'edit_form': PropertyForm(instance=property_instance),
        'edit_images_form': PropertyImagesForm(),
    })


@login_required
@require_POST
def property_edit(request, property_id):
    property_instance = get_object_or_404(Property, pk=property_id, owner=request.user)
    details_form = PropertyForm(request.POST, instance=property_instance)
    images_form = PropertyImageEditForm(
        request.POST,
        request.FILES,
        image_titles=request.POST.getlist('image_titles'),
        property_instance=property_instance,
    )
    if not all([details_form.is_valid(), images_form.is_valid()]):
        return JsonResponse({
            'errors': [
                f'{form.fields[name].label}. {message}' if name in form.fields else message
                for form in (details_form, images_form)
                for name, messages_for_field in form.errors.items()
                for message in messages_for_field
            ],
        }, status=400)

    edited_fields = request.POST.get('edited_fields')
    fields_to_update = details_form.changed_data if edited_fields is None else edited_fields.split(',')
    try:
        update_property(
            owner=request.user,
            property_id=property_id,
            details={
                name: value for name, value in details_form.cleaned_data.items()
                if name in fields_to_update
            },
            images=images_form.cleaned_data['images'],
            image_titles=images_form.cleaned_data.get('image_titles'),
            removed_image_ids=(photo.pk for photo in images_form.cleaned_data['removed_images']),
        )
    except Property.DoesNotExist as error:
        raise Http404 from error
    except ValidationError as error:
        return JsonResponse({'errors': error.messages}, status=400)
    except OSError:
        return JsonResponse({'errors': ['Não foi possível salvar as fotos. Tente novamente.']}, status=503)

    messages.success(request, 'Alterações salvas.')
    return JsonResponse({'redirect': reverse('property_manage', args=[property_id])})


@login_required
@require_POST
def property_image_delete(request, image_id):
    try:
        property_id = delete_property_image(owner=request.user, image_id=image_id)
    except PropertyImage.DoesNotExist as error:
        raise Http404 from error

    messages.success(request, 'Foto removida do imóvel.')
    return redirect('property_manage', property_id=property_id)
