from rest_framework import serializers


class QuestionSerializer(serializers.Serializer):
    question_index = serializers.IntegerField(min_value=1)
    is_correct = serializers.BooleanField()
    reaction_time_ms = serializers.IntegerField(min_value=0)
    trial_type = serializers.ChoiceField(choices=['repeat', 'switch'])
    error_type = serializers.ChoiceField(
        choices=['persistent', 'random'], allow_null=True, required=False
    )


class MarketSortSubmitSerializer(serializers.Serializer):
    session_id = serializers.CharField(max_length=64)
    is_complete = serializers.BooleanField()
    questions = QuestionSerializer(many=True)