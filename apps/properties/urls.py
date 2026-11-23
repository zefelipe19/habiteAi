from django.urls import path
from . import views as v

urlpatterns = [
    path('', v.index, name='index'),
    path('imoveis/novo/', v.property_create, name='property_create'),
    path('imoveis/meus/', v.my_properties, name='my_properties'),
    path('imoveis/<int:property_id>/', v.property_detail, name='property_detail'),
    path('imoveis/<int:property_id>/gerenciar/', v.property_manage, name='property_manage'),
    path('imoveis/<int:property_id>/editar/', v.property_edit, name='property_edit'),
    path('imoveis/fotos/<int:image_id>/remover/', v.property_image_delete, name='property_image_delete'),
]
