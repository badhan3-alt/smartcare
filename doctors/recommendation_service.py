import datetime

from appointments.queue_service import get_doctor_live_queue_summary


def get_doctor_recommendation(patient, doctor, department_id=None, appointment_date=None):
    """Score a doctor for a specific patient and explain the recommendation."""
    if appointment_date is None:
        appointment_date = datetime.date.today()

    score = 20
    reasons = []

    if department_id and doctor.department_id == department_id:
        score += 20
        reasons.append('Matches your specialty')

    if doctor.is_available:
        score += 12
        reasons.append('Available today')
    else:
        score -= 8
        reasons.append('Currently unavailable')

    rating = float(getattr(doctor, 'average_rating', 5.0) or 5.0)
    score += min(12, rating * 2.2)
    reasons.append(f'{rating:.1f}/5 patient rating')

    score += min(10, doctor.experience_years)
    reasons.append(f'{doctor.experience_years} years experience')

    if patient and doctor.appointments.filter(patient=patient).exists():
        score += 8
        reasons.append('You have seen this doctor before')

    queue_summary = get_doctor_live_queue_summary(doctor, appointment_date)
    pending_minutes = queue_summary.get('pending_minutes', 0)
    if pending_minutes <= 30:
        score += 8
        reasons.append('Shorter queue')
    elif pending_minutes >= 90:
        score -= 8
        reasons.append('Busy queue')

    if doctor.consultation_fee and doctor.consultation_fee <= 600:
        score += 6
        reasons.append('Affordable consultation')

    score = max(0, min(100, int(round(score))))

    unique_reasons = []
    seen = set()
    for reason in reasons:
        if reason not in seen:
            unique_reasons.append(reason)
            seen.add(reason)

    return {
        'score': score,
        'reasons': unique_reasons[:3],
    }


def get_recommended_doctors(patient, doctors_queryset, department_id=None, appointment_date=None, limit=3):
    """Return a ranked list of recommended doctors with AI explanation."""
    if appointment_date is None:
        appointment_date = datetime.date.today()

    ranked = []
    for doctor in doctors_queryset:
        recommendation = get_doctor_recommendation(
            patient=patient,
            doctor=doctor,
            department_id=department_id,
            appointment_date=appointment_date,
        )
        ranked.append({
            'doctor': doctor,
            'score': recommendation['score'],
            'reasons': recommendation['reasons'],
        })

    ranked.sort(key=lambda item: item['score'], reverse=True)
    return ranked[:limit]
