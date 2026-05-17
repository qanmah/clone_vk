from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/<str:username>/', views.user_profile, name='user_profile'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),
    path('add_friend/<str:username>/', views.send_friend_request, name='send_friend_request'),
    path('accept_request/<int:request_id>/', views.accept_friend_request, name='accept_request'),
    path('reject_request/<int:request_id>/', views.reject_friend_request, name='reject_request'),
    path('unfollow/<str:username>/', views.unfollow, name='unfollow'),
    path('followers/<str:username>/', views.followers_list, name='followers'),
    path('following/<str:username>/', views.following_list, name='following'),
    path('mark_read/<int:request_id>/', views.mark_read, name='mark_read'),
    path('mark_all_read/', views.mark_all_read, name='mark_all_read'),
    path('chat/', views.chat, name='chat'),
    path('chat/<str:username>/', views.chat, name='chat_with_user'),
    path("message/<int:message_id>/delete/", views.delete_message, name="delete_message"),
    path("message/<int:message_id>/edit/", views.edit_message, name="edit_message"),
    path("message/<int:message_id>/pin/", views.pin_message, name="pin_message"),
    path("message/<int:message_id>/unpin/", views.unpin_message, name="unpin_message"),
    path("chat/<str:username>/photo/", views.send_chat_photo, name="send_chat_photo"),
]