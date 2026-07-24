from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, PersonalGroup, GroupReview


class CustomUserCreationForm(UserCreationForm):
    """
    Custom registration form extending Django's built-in UserCreationForm.
    Includes username, email, and custom account_type ('listener' vs 'artist') choice field.
    """
    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('email', 'account_type',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control'})
        if 'account_type' in self.fields:
            self.fields['account_type'].widget.attrs.update({'class': 'form-select'})


class PersonalGroupForm(forms.ModelForm):
    """
    Form for creating and editing a user's PersonalGroup.
    """
    class Meta:
        model = PersonalGroup
        fields = ['name', 'description', 'is_public']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter group title (e.g. 70s Synth & Baroque Mix)',
                'required': True
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional description of this collection...'
            }),
            'is_public': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        labels = {
            'is_public': 'Make this Personal Group Publicly Viewable'
        }


class GroupReviewForm(forms.ModelForm):
    """
    Form for submitting ratings and reviews for a PersonalGroup.
    """
    class Meta:
        model = GroupReview
        fields = ['rating', 'review_text']
        widgets = {
            'rating': forms.Select(attrs={
                'class': 'form-select form-select-sm',
                'required': True
            }),
            'review_text': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'Write your thoughts on this group...',
                'required': True
            }),
        }

class UserUpdateForm(forms.ModelForm):
    """
    Form for a user to update their profile information.
    """
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'style': 'background-color: #282828; color: white; border-color: #3e3e3e;',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'style': 'background-color: #282828; color: white; border-color: #3e3e3e;',
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'style': 'background-color: #282828; color: white; border-color: #3e3e3e;',
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'style': 'background-color: #282828; color: white; border-color: #3e3e3e;',
            }),
        }
