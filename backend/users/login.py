"""Signing in."""
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView


class LoginSerializer(TokenObtainPairSerializer):
    """The stock sign-in, except that it says so when an account is suspended.

    Django turns a suspended (inactive) account away exactly as it turns away a
    wrong password, which would leave the person retyping a password that is
    right. They are told only once the password is right, so the answer gives
    nothing away to someone guessing; and the password is checked once on every
    path, as it would have been anyway, so neither answer takes longer to give.
    """
    default_error_messages = {
        'account_suspended': 'This account has been suspended. Ask your Super Admin to reactivate it.',
    }

    def validate(self, attrs):
        from .models import User
        username = attrs.get(self.username_field)
        person = (User._default_manager.filter(**{self.username_field: username}).first()
                  if username else None)
        if person is not None and person.is_suspended:
            if person.check_password(attrs.get('password') or ''):
                # A dict, so the code reaches the client beside the message and
                # the sign-in screen can show this one as it is.
                raise AuthenticationFailed({'detail': self.error_messages['account_suspended'],
                                            'code': 'account_suspended'})
            raise AuthenticationFailed(self.error_messages['no_active_account'], 'no_active_account')
        return super().validate(attrs)


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
