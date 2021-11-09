import os
from django.contrib.auth.models import AnonymousUser
from django.shortcuts import reverse, redirect, render
from django_google.flow import DjangoFlow, CLIENT_SECRET_FILE, SCOPES
from django.http.request import HttpRequest
from django.http.response import HttpResponsePermanentRedirect, HttpResponseRedirect, JsonResponse
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

    if isinstance(request.user, AnonymousUser):
        return HttpResponseRedirect('/')

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
    return render(request, 'generic_form.html', {'form': form})


def handle_video_id(request: HttpRequest):

    if isinstance(request.user, AnonymousUser):
        return HttpResponseRedirect('/')

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

                title = results["items"][0]["snippet"]["title"]
                channel_id = results["items"][0]["snippet"]["channelId"]

                request.session['video_id'] = form.cleaned_data['video_id']
                request.session['video_title'] = title
                request.session['channel_id'] = channel_id

                service.close()

                return HttpResponseRedirect('/confirm_video')
    else:
        return HttpResponseRedirect('/input_mode')

    return render(request, 'generic_form.html', {'form': form, 'prev': '/input_mode'})


def handle_video_confirmation(request: HttpRequest):

    form = forms.ConfirmForm()

    if isinstance(request.user, AnonymousUser):
        return HttpResponseRedirect('/')
    
    if 'video_id' not in request.session or 'video_title' not in request.session:
        return HttpResponseRedirect('/input_video_id')

    if 'mode' in request.session and request.session['mode'] == '1':
        if request.method == 'POST':
            return HttpResponseRedirect('/input_spammer_id')
    else:
        return HttpResponseRedirect('/input_mode')

    return render(request, 'confirm.html', {
        'form': form, 'message': f'Chosen Video: {request.session["video_id"]}\nIs this correct?',
        'prev': '/input_video_id'
    })


def handle_channel_id(request):

    if isinstance(request.user, AnonymousUser):
        return HttpResponseRedirect('/')

    form = forms.ChannelIdForm()

    if 'mode' in request.session and request.session['mode'] == '2':
        if request.method == 'POST':
            form = forms.ChannelIdForm(request.POST)

            if form.is_valid():
                request.session['channel_id'] = form.cleaned_data['channel_id']
                request.session['max_comments'] = form.cleaned_data['max_comments']
                return HttpResponseRedirect('/input_spammer_id')

    else:
        return HttpResponseRedirect('/input_mode')

    return render(request, 'generic_form.html', {'form': form, 'prev': '/input_mode'})


def handle_spammer_id(request):

    if isinstance(request.user, AnonymousUser):
        return HttpResponseRedirect('/')

    form = forms.SpammerIdForm()

    if request.method == 'POST':
        form = forms.SpammerIdForm(request.POST)

        if form.is_valid():
            request.session['spammer_id'] = form.cleaned_data['spammer_id']

            if request.session['channel_id'] == request.session['spammer_id']:
                if request.session['mode'] == '2':
                    request.session['error'] = (
                        'WARNING - You are scanning for your own channel ID!\n'
                        'For safety purposes, this program\'s delete functionality is disabled when scanning for yourself across your entire channel (Mode 2).\n'
                        'If you want to delete your own comments for testing purposes, you can instead scan an individual video (Mode 1).'
                    )

                    return HttpResponseRedirect('/input_mode')
                else:
                    request.session['warning'] = (
                        'WARNING: You are scanning for your own channel ID! This would delete all of your comments on the video!\n'
                        '     (You WILL still be asked to confirm before actually deleting anything)\n'
                        'If you are testing and want to scan and/or delete your own comments, confirm below, or select \'Back\' to enter a new spammer ID'
                    )
            
                    return HttpResponseRedirect('/confirm_self_deletion')

            fieldsToFetch = (
                'nextPageToken,items/snippet/topLevelComment/id,items/snippet/totalReplyCount,'
                'items/snippet/topLevelComment/snippet/authorChannelId/value,'
                'items/snippet/topLevelComment/snippet/videoId'
            )

            auth: GoogleAuth = GoogleAuth.objects.get(user=request.user)
            service: Resource = build(API_SERVICE_NAME, API_VERSION, auth.creds)

            next_page_token = None
            com_count = 0
            repl_count = 0
            spam_comment_ids = []
            vid_id_dict = {}

            id_arg = {
                'videoId': request.session['video_id']
            } if request.session['mode'] == '1' else {
                'allThreadsRelatedToChannelId': request.session['channel_id']
            }

            while next_page_token != 'end':
                results = service.commentThreads().list(
                    part="snippet",
                    maxResults=100, # 100 is the max per page allowed by YouTube, but multiple pages will be scanned
                    pageToken=next_page_token,
                    fields=fieldsToFetch,
                    textFormat="plainText",
                    **id_arg
                ).execute()

                next_page_token = results['nextPageToken'] if 'nextPageToken' in results else 'end'

                for item in results["items"]:
                    comment = item["snippet"]["topLevelComment"]
                    author_channel_id = item["snippet"]["topLevelComment"]["snippet"]["authorChannelId"]["value"]
                    video_id = comment["snippet"]["videoId"] # Only enable if NOT checking specific video
                    parent_id = item["snippet"]["topLevelComment"]["id"]
                    num_replies = item["snippet"]["totalReplyCount"]
                    com_count += 1  # Counts number of comments scanned, add to global count

                    if author_channel_id == request.session['spammer_id']:
                        spam_comment_ids.append(parent_id)
                        vid_id_dict[parent_id] = video_id

                    if num_replies > 0:
                        repl_results = service.comments().list(
                            part="snippet",
                            parentId=parent_id,
                            maxResults=100, # 100 is the max per page, but multiple pages will be scanned
                            fields="items/snippet/authorChannelId/value,items/id",
                            textFormat="plainText"
                        )

                        for item in repl_results['items']:
                            repl_author_channel_id = item['snippet']['authorChannelId']['value']
                            reply_id = item['id']
                            repl_count += 1
                        
                        if repl_author_channel_id == request.session['spammer_id']:
                            spam_comment_ids.append(reply_id)
                            vid_id_dict[reply_id] = video_id

            message = (
                f'Top Level Comments Scanned: {com_count} | Replies Scanned: {repl_count} |'
                f' Number of Spammer Comments Found: {len(spam_comment_ids)}\n'
                'Spam comments ready to display'
            )


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
        user = User.objects.create(
            email=userinfo['email'],
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
                user = User.objects.create(
                    email=userinfo['email'],
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