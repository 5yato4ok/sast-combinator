from django.urls import path

from . import views

urlpatterns = [
    path("search/", views.search_users, name="user_search"),
    path("user/<int:id>/", views.get_user_by_id, name="user_detail"),
]
