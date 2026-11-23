from django.urls import path

from .views import profile_settings


app_name = 'profile'

urlpatterns = [
    path('', profile_settings, name='settings'),
]
