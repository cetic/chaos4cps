"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
# for static files (css, js, images and so on)
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.conf.urls.static import static
from django.conf import settings
from .views import custom_logout, home, version_report, get_version_details_text, save_version_data

urlpatterns = [
    #path('jet/', include('jet.urls', 'jet')),  # Django JET URLS
    #path('jet/dashboard/', include('jet.dashboard.urls', 'jet-dashboard')),  # Django JET dashboard URLS
    path('admin/logout/', custom_logout, name='logout'),
    # Version report URLs
    path('version/<uuid:version_uuid>/report/', version_report, name='version_report'),

    path('version/<uuid:version_uuid>/details-text/', get_version_details_text, name='get_version_details_text'),
    path('version/<uuid:version_uuid>/save-data/', save_version_data, name='save_version_data'),

    path('admin/', admin.site.urls), 
    path('', home, name='home'), 
]

urlpatterns += staticfiles_urlpatterns()
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)