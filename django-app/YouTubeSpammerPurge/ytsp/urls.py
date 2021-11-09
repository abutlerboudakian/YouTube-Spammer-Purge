from django.urls import path
from . import views

urlpatterns = [
    path('', views.oAuthJavascriptView, name="login"),
    path('auth/', views.oAuthView, name="auth"),
    path('oauth2callback/', views.oAuth2CallBackView, name="oauth2callback"),
    path('input_mode', views.handle_mode, name='input_mode'),
    path('input_video_id', views.handle_video_id, name='input_video_id')
]