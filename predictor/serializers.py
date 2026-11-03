import math

from rest_framework import serializers


class PredictionSerializer(serializers.Serializer):

    age = serializers.IntegerField(min_value=1, max_value=120)
    sex = serializers.ChoiceField(
        choices=["male", "female"]
    )
    bmi = serializers.FloatField(min_value=10, max_value=100)
    children = serializers.IntegerField(min_value=0, max_value=20)
    smoker = serializers.ChoiceField(
        choices=["yes", "no"]
    )
    region = serializers.ChoiceField(
        choices=[
            "southwest",
            "southeast",
            "northwest",
            "northeast"
        ]
    )

    def validate_bmi(self, value):
        if not math.isfinite(value):
            raise serializers.ValidationError('Enter a finite BMI between 10 and 100.')
        return value
