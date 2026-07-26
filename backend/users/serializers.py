from rest_framework import serializers
from .models import User, WorkspaceTeam, Branch


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


class UserSerializer(serializers.ModelSerializer):
    role_label = serializers.CharField(source='get_role_display', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True, default=None)
    # Whether the caller may edit/remove this account — lets the Team page hide
    # controls that the API would refuse anyway.
    can_manage = serializers.SerializerMethodField()

    def get_can_manage(self, obj):
        request = self.context.get('request')
        actor = getattr(request, 'user', None)
        if actor is None or not actor.is_authenticated:
            return False
        return bool(actor.pk == obj.pk or actor.can_manage(obj))

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'password',
                  'role', 'role_label', 'branch', 'branch_name', 'can_manage',
                  'is_staff', 'is_manager', 'is_general_manager', 'team', 'phone', 'voxbay_extension']
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
