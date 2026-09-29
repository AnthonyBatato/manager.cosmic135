from django.urls import path, re_path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("pages/", views.page_list, name="page_list"),
    path("pages/new/", views.page_create, name="page_create"),
    path("pages/<int:pk>/", views.page_edit, name="page_edit"),
    path("pages/<int:pk>/source/", views.page_source_download, name="page_source_download"),
    path("pages/<int:pk>/upload/", views.page_upload, name="page_upload"),
    path("pages/<int:pk>/preview/", views.page_preview, name="page_preview"),
    path("pages/<int:pk>/preview-assets/<path:path>", views.preview_asset, name="preview_asset"),
    path("preview-public/<int:pk>/<str:token>/", views.public_preview, name="public_preview"),
    path("preview-assets-public/<int:pk>/<str:token>/<path:path>", views.public_preview_asset, name="public_preview_asset"),
    path("pages/<int:pk>/publish/", views.page_publish, name="page_publish"),
    path("pages/<int:pk>/actions/new/", views.action_create, name="action_create"),
    path("pages/<int:pk>/domains/new/", views.domain_create, name="domain_create"),
    path("pages/<int:pk>/domains/<int:domain_pk>/verify/", views.domain_verify, name="domain_verify"),
    path("pages/<int:pk>/rollback/<int:version>/", views.page_rollback, name="page_rollback"),
    path("p/<slug:slug>/", views.local_public_page, name="local_public_page"),
    path("p/<slug:page_slug>/assets/<path:path>", views.public_asset, name="public_asset"),
    path("r/<slug:page_slug>/<slug:action_key>/", views.action_redirect, name="action_redirect"),
    path("api/domains/allow-certificate/", views.allow_certificate, name="allow_certificate"),
    re_path(r"^(?P<path>.+)$", views.public_host_asset, name="public_host_asset"),
]
