from django import forms
from . import validators

class ModeForm(forms.Form):
    MODE_CHOICES = [
        ('1', 'Scan Single Video'),
        ('2', 'Scan Entire Channel'),
    ]

    mode = forms.ChoiceField(MODE_CHOICES, required=True, label='Do you want to scan a single video, or your entire channel?')

class VideoIdForm(forms.Form):
    video_id = forms.CharField(max_length=11, required=True, validators=[validators.validate_video_id], label='Enter Video ID to scan:')

class ChannelIdForm(forms.Form):
    channel_id = forms.CharField(max_length=24, required=True, validators=[validators.validate_channel_id], label='Enter YOUR Channel ID:')
    max_comments = forms.IntegerField(min_value=1, required=True, label='Enter the maximum number of comments to scan:')

class ConfirmForm(forms.Form):
    any_field = forms.HiddenInput()

class SpammerIdForm(forms.Form):
    spammer_id = forms.CharField(max_length=24, required=True, validators=validators.validate_channel_id, label='Enter the Channel ID of the spammer:')

