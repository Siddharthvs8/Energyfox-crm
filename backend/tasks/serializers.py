from rest_framework import serializers
from .models import Task
from users.serializers import UserSerializer


class MinimalLeadSerializer(serializers.Serializer):
    """Lightweight serializer for lead details embedded in task responses."""
    id = serializers.IntegerField()
    first_name = serializers.CharField()
    last_name = serializers.CharField(allow_null=True, allow_blank=True, default='')
    email = serializers.EmailField(allow_null=True, default=None)
    phone = serializers.CharField(allow_null=True, allow_blank=True, default='')


class TaskSerializer(serializers.ModelSerializer):
    assignee_details = UserSerializer(source='assignee', read_only=True)
    lead_details = MinimalLeadSerializer(source='lead', read_only=True)

    class Meta:
        model = Task
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'reminded_at', 'overdue_reminded_at']

    def validate_assignee(self, person):
        """A suspended account takes on no new work. Refused only as a change, so
        a task still with someone suspended can be edited until it is handed on."""
        if (person is not None and person.is_suspended
                and getattr(self.instance, 'assignee_id', None) != person.pk):
            name = f"{person.first_name} {person.last_name}".strip() or person.username
            raise serializers.ValidationError(f"{name}'s account is suspended — pick someone else.")
        return person
