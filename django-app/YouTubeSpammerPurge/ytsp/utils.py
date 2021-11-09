from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

def validate_video_id(video_id):
  if len(video_id) != 11:
    raise ValidationError(
        _("Invalid Video ID %(value)s! Video IDs are 11 characters long."),
        params={'value': video_id}
    )


def validate_channel_id(channel_id):
  if not (len(channel_id) == 24 or channel_id[0:2] == "UC"):
    raise ValidationError(
        _("Invalid Video ID %(value)s! Video IDs are 11 characters long."),
        params={'value': channel_id}
    )
