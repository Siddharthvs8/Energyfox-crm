from rest_framework import serializers
from .models import User, WorkspaceTeam, Branch, CustomRole


class BranchSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(source='members.count', read_only=True)
    manager_name = serializers.SerializerMethodField()
    lead_count = serializers.SerializerMethodField()
    members = serializers.SerializerMethodField()

    class Meta:
        model = Branch
        fields = ['id', 'name', 'code', 'manager', 'manager_name', 'location', 'address',
                  'phone', 'email', 'is_active', 'member_count', 'lead_count', 'members',
                  'created_at']
        read_only_fields = ['created_at']

    def get_manager_name(self, obj):
        u = obj.manager
        if not u:
            return None
        return f"{u.first_name} {u.last_name}".strip() or u.username

    def get_lead_count(self, obj):
        """Leads owned by this branch's staff (excludes trashed)."""
        from leads.models import Lead
        return Lead.objects.filter(assigned_to__branch=obj, is_trashed=False).count()

    def get_members(self, obj):
        return [{
            'id': u.id,
            'name': f"{u.first_name} {u.last_name}".strip() or u.username,
            'role': u.role,
            'role_label': u.get_role_display(),
        } for u in obj.members.all().order_by('first_name', 'username')]


class CustomRoleSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(source='members.count', read_only=True)

    class Meta:
        model = CustomRole
        fields = ['id', 'name', 'description', 'permissions', 'is_active',
                  'member_count', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def validate_permissions(self, value):
        from .permission_catalog import ALL_PERMISSION_KEYS, clean_permissions
        if not isinstance(value, list):
            raise serializers.ValidationError('Expected a list of permission keys.')
        unknown = [str(v) for v in value if str(v) not in ALL_PERMISSION_KEYS]
        if unknown:
            raise serializers.ValidationError(f"Unknown permission(s): {', '.join(unknown)}")
        return clean_permissions(value)


class UserSerializer(serializers.ModelSerializer):
    role_label = serializers.CharField(source='get_role_display', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True, default=None)
    # Whether the caller may edit/remove this account — lets the Team page hide
    # controls that the API would refuse anyway.
    can_manage = serializers.SerializerMethodField()
    # Absolute URL so the frontend can use it directly (MEDIA_URL is relative in
    # local dev and an S3 domain in production).
    avatar_url = serializers.SerializerMethodField()
    custom_role_name = serializers.CharField(source='custom_role.name', read_only=True, default=None)
    # Resolved permission keys — empty for built-in roles, whose access comes from
    # the role rules rather than a list. Drives the sidebar for custom users.
    permissions = serializers.SerializerMethodField()
    # This account can look but not touch. Sent as its own flag rather than
    # leaving the client to match on the role string, so the "View only" banner
    # and the hidden write controls key off the same thing the server enforces.
    read_only = serializers.BooleanField(source='is_spectator', read_only=True)

    def get_permissions(self, obj):
        # Same order as the role itself reports (catalogue order), so the two
        # endpoints can't disagree about a role's contents.
        if obj.granted is None:
            return []
        return list(obj.custom_role.permissions or [])

    # Any authenticated user may set their own picture, so bound the upload here
    # rather than trusting the browser.
    AVATAR_MAX_BYTES = 5 * 1024 * 1024
    AVATAR_TYPES = ('image/jpeg', 'image/png', 'image/webp', 'image/gif')

    def validate_avatar(self, value):
        if not value:
            return value
        if value.size > self.AVATAR_MAX_BYTES:
            raise serializers.ValidationError('Picture must be 5 MB or smaller.')
        content_type = getattr(value, 'content_type', None)
        if content_type and content_type not in self.AVATAR_TYPES:
            raise serializers.ValidationError('Use a JPEG, PNG, WebP or GIF image.')
        return value

    def get_avatar_url(self, obj):
        if not obj.avatar:
            return None
        url = obj.avatar.url
        request = self.context.get('request')
        return request.build_absolute_uri(url) if request else url

    def get_can_manage(self, obj):
        request = self.context.get('request')
        actor = getattr(request, 'user', None)
        if actor is None or not actor.is_authenticated:
            return False
        return bool(actor.pk == obj.pk or actor.can_manage(obj))

    # Which wholesale modules this user reaches, and whether they may write:
    # {'items': 'rw', 'proforma': 'r', …}. Sent so the sidebar and the write
    # controls are decided from the same table the API enforces.
    b2b_access = serializers.SerializerMethodField()

    def get_b2b_access(self, obj):
        from inventory.b2b_access import access_map
        return access_map(obj)

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'password',
                  'role', 'role_label', 'branch', 'branch_name', 'can_manage',
                  'avatar', 'avatar_url', 'custom_role', 'custom_role_name', 'permissions',
                  'is_staff', 'is_manager', 'is_general_manager', 'read_only',
                  'team', 'phone', 'voxbay_extension', 'b2b_access']
        extra_kwargs = {
            'password': {'write_only': True},
        }
        # Driven by `role` now — never set directly.
        read_only_fields = ['is_staff', 'is_manager', 'is_general_manager']

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = super().create(validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user

class WorkspaceTeamSerializer(serializers.ModelSerializer):
    members_detail = UserSerializer(source='members', many=True, read_only=True)
    manager_detail = UserSerializer(source='manager', read_only=True)
    member_ids = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='members', many=True, write_only=True, required=False
    )

    class Meta:
        model = WorkspaceTeam
        fields = ['id', 'name', 'manager', 'manager_detail', 'members_detail', 'member_ids', 'created_at']

    def create(self, validated_data):
        members = validated_data.pop('members', [])
        team = WorkspaceTeam.objects.create(**validated_data)
        for member in members:
            member.team = team
            member.save()
        return team

    def update(self, instance, validated_data):
        members = validated_data.pop('members', None)
        instance.name = validated_data.get('name', instance.name)
        instance.manager = validated_data.get('manager', instance.manager)
        instance.save()

        if members is not None:
            # Clear current members and set new ones
            User.objects.filter(team=instance).update(team=None)
            for member in members:
                member.team = instance
                member.save()
        
        return instance
