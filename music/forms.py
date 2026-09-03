from django import forms

from music.auth import users

DARK_INPUT = {
    'class': 'form-control',
    'style': 'background-color:#242424;color:#fff;border-color:#3e3e3e;',
}


class RegistrationForm(forms.Form):

    username = forms.CharField(
        min_length=3, max_length=150,
        widget=forms.TextInput(attrs={**DARK_INPUT, 'placeholder': 'Choose a username'}),
        help_text='At least 3 characters. Letters, digits and @ . + - _ only.',
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={**DARK_INPUT, 'placeholder': 'you@example.com'}),
    )
    account_type = forms.ChoiceField(
        choices=(('listener', 'Listener'), ('artist', 'Artist')),
        widget=forms.Select(attrs={
            'class': 'form-select',
            'style': 'background-color:#242424;color:#fff;border-color:#3e3e3e;',
        }),
        help_text='Listeners browse and build playlists. Artists can also manage their own tracks.',
    )
    password1 = forms.CharField(
        label='Password', min_length=8,
        widget=forms.PasswordInput(attrs={**DARK_INPUT, 'placeholder': 'At least 8 characters'}),
    )
    password2 = forms.CharField(
        label='Confirm password',
        widget=forms.PasswordInput(attrs={**DARK_INPUT, 'placeholder': 'Type it again'}),
    )

    def clean_username(self):
        username = self.cleaned_data['username'].strip()

        if not all(c.isalnum() or c in '@.+-_' for c in username):
            raise forms.ValidationError(
                'Use only letters, digits and the characters @ . + - _'
            )

        if users.username_exists(username):
            raise forms.ValidationError('That username is already taken.')

        return username

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip()
        if email and users.email_exists(email):
            raise forms.ValidationError('An account already uses that email address.')
        return email

    def clean_account_type(self):
        value = self.cleaned_data['account_type']
        return value if value in ('listener', 'artist') else 'listener'

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get('password1'), cleaned.get('password2')

        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'The two passwords do not match.')

        if p1 and p1.isdigit():
            self.add_error('password1', 'Your password cannot be entirely numeric.')

        if p1 and cleaned.get('username') and p1.lower() == cleaned['username'].lower():
            self.add_error('password1', 'Your password cannot be your username.')

        return cleaned

    def save(self):
        data = self.cleaned_data
        return users.create_user(
            username=data['username'],
            raw_password=data['password1'],
            email=data.get('email', ''),
            account_type=data['account_type'],
        )


class LoginForm(forms.Form):

    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={**DARK_INPUT, 'autofocus': True}),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs=DARK_INPUT),
    )


class TrackUploadForm(forms.Form):

    title = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={**DARK_INPUT, 'placeholder': 'Track title'}),
    )
    album_choice = forms.CharField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select',
                                   'style': 'background-color:#242424;color:#fff;border-color:#3e3e3e;'}),
        help_text='Add to one of your albums, or leave blank to start a new one.',
    )
    new_album_title = forms.CharField(
        required=False, max_length=255,
        widget=forms.TextInput(attrs={**DARK_INPUT, 'placeholder': 'New album title'}),
    )
    genre = forms.CharField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select',
                                   'style': 'background-color:#242424;color:#fff;border-color:#3e3e3e;'}),
    )
    audio = forms.FileField(
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'audio/*'}),
        help_text='MP3, OGG, WAV or M4A.',
    )
    duration_sec = forms.IntegerField(required=False, min_value=0, max_value=36000,
                                      widget=forms.HiddenInput())

    def __init__(self, *args, albums=None, genres=None, **kwargs):
        super().__init__(*args, **kwargs)
        album_choices = [('', '— Create a new album —')]
        album_choices += [(str(a.id), a.title) for a in (albums or [])]
        self.fields['album_choice'].widget.choices = album_choices
        self.fields['genre'].widget.choices = [('', 'Uncategorised')] + [
            (g.name, g.name) for g in (genres or [])
        ]
        self._album_ids = {str(a.id) for a in (albums or [])}

    def clean_album_choice(self):
        value = (self.cleaned_data.get('album_choice') or '').strip()
        if value and value not in self._album_ids:
            raise forms.ValidationError('That album does not belong to you.')
        return value

    def clean_audio(self):
        from django.conf import settings
        import os

        upload = self.cleaned_data['audio']
        name = (upload.name or '').lower()
        ext = os.path.splitext(name)[1]

        if ext not in settings.ALLOWED_AUDIO_EXTENSIONS:
            raise forms.ValidationError(
                'Unsupported file type. Allowed: '
                + ', '.join(settings.ALLOWED_AUDIO_EXTENSIONS)
            )

        limit = settings.MAX_AUDIO_UPLOAD_MB * 1024 * 1024
        if upload.size > limit:
            raise forms.ValidationError(
                f'File is {upload.size // (1024*1024)} MB; the limit is '
                f'{settings.MAX_AUDIO_UPLOAD_MB} MB.'
            )
        if upload.size == 0:
            raise forms.ValidationError('That file is empty.')

        return upload

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('album_choice') and not (cleaned.get('new_album_title') or '').strip():
            self.add_error('new_album_title',
                           'Give a title for the new album, or pick an existing one.')
        return cleaned


class ArtistProfileForm(forms.Form):

    name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={**DARK_INPUT, 'placeholder': 'Stage or band name'}),
    )
    bio = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={**DARK_INPUT, 'rows': 3,
                                     'placeholder': 'Tell listeners about your music...'}),
    )
