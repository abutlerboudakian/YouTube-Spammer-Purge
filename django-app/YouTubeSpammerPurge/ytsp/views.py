import os
from django.shortcuts import reverse, redirect, render
from django_google.flow import DjangoFlow, CLIENT_SECRET_FILE, SCOPES
from django.http.request import HttpRequest
from django.http.response import HttpResponseRedirect, JsonResponse
from django.contrib.auth import get_user_model
from django.conf import settings
from django_google.models import GoogleAuth
from googleapiclient.discovery import build, Resource
from . import forms

API_SERVICE_NAME = "youtube"
API_VERSION = "v3"

def not_broken_constructor(self, oauth2session, client_type, client_config, redirect_uri=None, code_verifier=None, autogenerate_code_verifier=None):
    os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
    super(DjangoFlow, self).__init__(oauth2session, client_type, client_config,  redirect_uri, code_verifier, autogenerate_code_verifier)

DjangoFlow.__init__ = not_broken_constructor

User = get_user_model()
flow = DjangoFlow.from_client_secrets_file(client_secrets_file=CLIENT_SECRET_FILE, scopes=SCOPES)

# Create your views here.

def handle_mode(request):

    form = forms.ModeForm()

    if request.method == 'POST':
        form = forms.ModeForm(request.POST)
        
        if form.is_valid():
            request.session['mode'] = form.cleaned_data['mode']
            if form.cleaned_data['mode'] == '1':
                return HttpResponseRedirect('/input_video_id')
            else:
                return HttpResponseRedirect('/input_channel_id')

    if 'mode' in request.session:
        del request.session['mode']
    return render(request, 'mode.html', {'form': form})


def handle_video_id(request: HttpRequest):

    form = forms.VideoIdForm()

    if 'mode' in request.session and request.session['mode'] == '1':
        if request.method == 'POST':
            form = forms.ModeForm(request.POST)

            if form.is_valid():

                auth: GoogleAuth = GoogleAuth.objects.get(user=request.user)
                service: Resource = build(API_SERVICE_NAME, API_VERSION, auth.creds)
                results = service.videos().list(
                    part="snippet",
                    id=form.cleaned_data['video_id'],
                    fields="items/snippet/title",
                    maxResults=1
                ).execute()

                title = results["items"][0]["snipped"]["title"]

                request.session['video_id'] = form.cleaned_data['video_id']
                request.session['video_title'] = title

                return HttpResponseRedirect('/confirm_video')
    else:
        return HttpResponseRedirect('/input_mode')

    return render(request, 'video_id.html', {'form': form})


def handle_video_confirmation(request: HttpRequest):

    pass


def handle_channel_id(request):

    form = forms.VideoIdForm()

    if 'mode' in request.session and request.session['mode'] == '2':
        if request.method == 'POST':
            form = forms.ModeForm(request.POST)

            if form.is_valid():
                return HttpResponseRedirect('/input_spammer_id')

    else:
        return HttpResponseRedirect('/input_mode')

    return render(request, 'video_id.html', {'form': form})



#
# GOOGLE AUTH ENDPOINTS
#
def oAuthView(request):
        callback_url=reverse("oauth2callback") # callback Url (oAuth2CallBackView URL)
        return redirect(flow.get_auth_url(request, callback_url=callback_url))

# Google Authentication Call Back VIEW (Using Without Javascript)
def oAuth2CallBackView(request):
    success_url = "/dashboard/"  # redirection URL on Success reverse() can b use here

    # Library a little sus if the public api has mispelled methods
    creds = flow.get_credentails_from_response_url(response_url=request.build_absolute_uri())
    
    userinfo = flow.get_userinfo(creds=creds)
    try:
        user = User.objects.get(email=userinfo['email'])
    except User.DoesNotExist:
        user = User.objects.create(email=userinfo['email'],
                                           username=userinfo['email'],
                                           first_name=userinfo['given_name'],
                                           last_name=userinfo['family_name']
                                       )
    finally:
        try:
            gauth = GoogleAuth.objects.get(user=user)
        except GoogleAuth.DoesNotExist:
            gauth = GoogleAuth.objects.create(user=user, creds=creds)

    # Return Response as you want or Redirect to some URL

def oAuthJavascriptView(request):
    if request.is_ajax():
        if request.method == "POST":
            code = request.POST.get('code')
            flow = DjangoFlow.from_client_secrets_file(client_secrets_file=CLIENT_SECRET_FILE, scopes=SCOPES)
            creds = flow.get_credentials_from_code(code=code, javascript_callback_url="https://example.org")
            userinfo = flow.get_userinfo(creds=creds)
            try:
                user = User.objects.get(email=userinfo['email'])
            except User.DoesNotExist:
                user = User.objects.create(email=userinfo['email'],
                                               username=userinfo['email'],
                                               first_name=userinfo['given_name'],
                                               last_name=userinfo['family_name']
                                           )
            finally:
                try:
                    gauth = GoogleAuth.objects.get(user=user)
                except GoogleAuth.DoesNotExist:
                    gauth = GoogleAuth.objects.create(user=user, creds=creds)
            # return JSON Response with Status Code of 200 for success and 400 for errors
            return JsonResponse({}, status=200)

    else:
        context = {
            "client_id": getattr(settings, 'GOOGLE_CLIENT_ID', None),
            "scopes": " ".join(SCOPES)
        }
        # Render HTML page that havs Google Authentication Page with Javasccript
        return render(request, 'login.html', context)