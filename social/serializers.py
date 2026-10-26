from rest_framework import serializers
from .models import Notification, Comment

class NotificationSerializer(serializers.ModelSerializer):
    notification_type_display = serializers.CharField(source='get_notification_type_display', read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id',
            'notification_type',
            'notification_type_display',
            'message',
            'target_url',
            'is_read',
            'created_at',
        ]

class CommentSerializer(serializers.ModelSerializer):
    text = serializers.CharField(source='content')

    class Meta:
        model = Comment
        fields = ['id', 'text', 'created_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        viewer = self.context['request'].user
        data['comment_id'] = data.pop('id')
        data['sender_name'] = '匿名'
        data['is_mine'] = instance.user_id == viewer.id
        return data