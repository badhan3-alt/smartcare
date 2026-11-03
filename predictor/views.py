import io
import logging
import math
import os

import joblib
import pandas as pd
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_GET
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view, authentication_classes, parser_classes, permission_classes, throttle_classes,
)
from rest_framework.exceptions import APIException, ParseError
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from .serializers import PredictionSerializer


logger = logging.getLogger(__name__)
MODEL_PATH = os.path.join(settings.BASE_DIR, 'ml', 'insurance_model.pkl')
SCALER_PATH = os.path.join(settings.BASE_DIR, 'ml', 'scaler.pkl')
_model = None
_scaler = None


class PredictionRequestTooLarge(APIException):
    status_code = 413
    default_detail = 'Prediction requests must be 8 KB or smaller.'


class PredictionJSONParser(JSONParser):
    """Reject oversized JSON before decoding or allocating its object tree."""

    def parse(self, stream, media_type=None, parser_context=None):
        payload = stream.read(8193)
        if len(payload) > 8192:
            raise PredictionRequestTooLarge()
        try:
            return super().parse(io.BytesIO(payload), media_type, parser_context)
        except RecursionError:
            raise ParseError('The JSON document is nested too deeply.') from None


class InsurancePredictionThrottle(UserRateThrottle):
    scope = 'insurance_prediction'
    rate = '30/min'


def _get_model_and_scaler():
    """Load trusted local artifacts lazily, preserving application startup."""
    global _model, _scaler
    if _model is None:
        _model = joblib.load(MODEL_PATH)
    if _scaler is None:
        _scaler = joblib.load(SCALER_PATH)
    return _model, _scaler


@login_required
@require_GET
def home(request):
    return render(request, 'predictor/index.html')


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([PredictionJSONParser])
@throttle_classes([InsurancePredictionThrottle])
def predict_insurance(request):
    serializer = PredictionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    data = serializer.validated_data
    try:
        model, scaler = _get_model_and_scaler()
        input_data = pd.DataFrame([{
            'age': data['age'], 'is_female': int(data['sex'] == 'female'),
            'bmi': data['bmi'], 'children': data['children'],
            'is_smoker': int(data['smoker'] == 'yes'),
            'region_southeast': int(data['region'] == 'southeast'),
            'bmi_category_Obese': int(data['bmi'] >= 30),
        }])
        scale_columns = ['age', 'bmi', 'children']
        input_data[scale_columns] = scaler.transform(input_data[scale_columns])
        prediction = float(model.predict(input_data)[0])
        if not math.isfinite(prediction) or prediction < 0:
            raise ValueError('Invalid model output')
    except Exception:
        # Neither patient inputs nor model paths/tracebacks belong in responses or logs.
        logger.warning('Insurance prediction service is unavailable.')
        return Response({
            'success': False,
            'detail': 'The insurance estimate is temporarily unavailable. Please try again later.',
        }, status=503)
    return Response({'success': True, 'predicted_charge': round(prediction, 2)})
