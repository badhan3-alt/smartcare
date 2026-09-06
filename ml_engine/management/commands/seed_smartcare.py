import datetime
import random
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from accounts.models import UserProfile
from doctors.models import Department, DoctorProfile, DoctorSchedule
from appointments.models import Appointment, PatientFeedback
from ml_engine.ml_service import predict_consultation_duration

class Command(BaseCommand):
    help = "Seeds SmartCare with realistic departments, specialist doctors, patients, and appointment queues."

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding SmartCare database for NEUB Project Work II...")

        # 1. Create Administrator
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@smartcare.local',
                'first_name': 'System',
                'last_name': 'Administrator',
                'is_staff': True,
                'is_superuser': True
            }
        )
        if created:
            admin_user.set_password('admin123')
            admin_user.save()
        UserProfile.objects.get_or_create(
            user=admin_user,
            defaults={'role': 'admin', 'phone': '01700000000', 'gender': 'M'}
        )
        self.stdout.write(self.style.SUCCESS(" [OK] Administrator ready: admin / admin123"))

        # 2. Departments
        departments_data = [
            ('Cardiology', 'cardiology', 'Specialized cardiovascular diagnostics and therapy', 'bi-heart-pulse'),
            ('Pediatrics', 'pediatrics', 'Comprehensive child healthcare and immunizations', 'bi-emoji-smile'),
            ('Dermatology', 'dermatology', 'Clinical and aesthetic skin care treatments', 'bi-bandaid'),
            ('Orthopedics', 'orthopedics', 'Musculoskeletal care, joint, and bone surgeries', 'bi-person-arms-up'),
            ('Neurology', 'neurology', 'Brain and central nervous system disorders', 'bi-diagram-3'),
            ('General Medicine', 'general-medicine', 'Primary healthcare, triage, and chronic care', 'bi-hospital'),
            ('ENT', 'ent', 'Ear, nose, throat and head-neck diagnostics', 'bi-ear'),
            ('Gynecology', 'gynecology', 'Maternal healthcare and obstetrics', 'bi-gender-female'),
        ]

        dept_objs = {}
        for name, code, desc, icon in departments_data:
            dept, _ = Department.objects.get_or_create(
                code=code,
                defaults={'name': name, 'description': desc, 'icon': icon, 'is_active': True}
            )
            dept_objs[name] = dept
        self.stdout.write(self.style.SUCCESS(f" [OK] Seeded {len(dept_objs)} clinical departments"))

        # 3. Doctors
        doctors_data = [
            ('dr.rahim', 'Abdur', 'Rahim', 'Cardiology', 'MBBS, FCPS (Cardiology), MD', 'Interventional Cardiologist', 12, 800.00, 'Room 102'),
            ('dr.fatima', 'Fatima', 'Begum', 'Pediatrics', 'MBBS, DCH, FCPS (Pediatrics)', 'Child Health & Neonatologist', 8, 600.00, 'Room 204'),
            ('dr.kamal', 'Kamal', 'Hossain', 'Orthopedics', 'MBBS, MS (Ortho), FICS', 'Joint Replacement Specialist', 15, 900.00, 'Room 108'),
            ('dr.nusrat', 'Nusrat', 'Jahan', 'Dermatology', 'MBBS, DDV, FCPS', 'Clinical Dermatologist & Laser', 6, 500.00, 'Room 305'),
            ('dr.tanvir', 'Tanvir', 'Ahmed', 'Neurology', 'MBBS, MD (Neurology)', 'Stroke & Brain Specialist', 10, 850.00, 'Room 401'),
            ('dr.salma', 'Salma', 'Khatun', 'General Medicine', 'MBBS, FCPS (Medicine)', 'Consultant Physician', 9, 450.00, 'Room 105'),
        ]

        doc_profiles = []
        for username, first, last, dept_name, qual, spec, exp, fee, room in doctors_data:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={'first_name': first, 'last_name': last, 'email': f"{username}@smartcare.local"}
            )
            if created:
                user.set_password('doctor123')
                user.save()

            UserProfile.objects.get_or_create(
                user=user,
                defaults={'role': 'doctor', 'phone': f"01711{random.randint(100000, 999999)}", 'gender': 'M' if 'dr.rahim' in username or 'dr.kamal' in username or 'dr.tanvir' in username else 'F'}
            )

            doc_profile, _ = DoctorProfile.objects.get_or_create(
                user=user,
                defaults={
                    'department': dept_objs[dept_name],
                    'qualification': qual,
                    'specialization': spec,
                    'experience_years': exp,
                    'consultation_fee': fee,
                    'room_number': room,
                    'is_available': True,
                    'bio': f"Dedicated specialist with {exp} years of clinical expertise at tertiary hospitals."
                }
            )
            doc_profiles.append(doc_profile)

            # 5 weekly working shifts
            for day_idx in range(5):
                DoctorSchedule.objects.get_or_create(
                    doctor=doc_profile,
                    day_of_week=day_idx,
                    defaults={
                        'start_time': datetime.time(9, 0),
                        'end_time': datetime.time(17, 0),
                        'slot_duration_minutes': 20,
                        'is_active': True
                    }
                )

        self.stdout.write(self.style.SUCCESS(f" [OK] Seeded {len(doc_profiles)} specialist doctors with schedules"))

        # 4. Patients
        patients_data = [
            ('patient1', 'Joyashis', 'Das', 'joyashis@student.neub.edu.bd', 'M', 23, 'O+', 'Sylhet, Bangladesh'),
            ('patient2', 'Tabassum', 'Khan', 'tabassum@student.neub.edu.bd', 'F', 22, 'A+', 'Sylhet, Bangladesh'),
            ('patient3', 'Atiya', 'Maishah', 'atiya@student.neub.edu.bd', 'F', 22, 'B+', 'Sylhet, Bangladesh'),
            ('patient4', 'Rana', 'Luthfur', 'rana@neub.edu.bd', 'M', 45, 'AB+', 'Amberkhana, Sylhet'),
            ('patient5', 'Rafiqul', 'Islam', 'rafiq@example.com', 'M', 58, 'B+', 'Zindabazar, Sylhet'),
        ]

        patient_users = []
        for username, first, last, email, gender, age, bg, addr in patients_data:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={'first_name': first, 'last_name': last, 'email': email}
            )
            if created:
                user.set_password('patient123')
                user.save()

            dob = datetime.date.today() - datetime.timedelta(days=int(age * 365.25))
            UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'role': 'patient',
                    'gender': gender,
                    'date_of_birth': dob,
                    'blood_group': bg,
                    'phone': f"01811{random.randint(100000, 999999)}",
                    'address': addr
                }
            )
            patient_users.append(user)

        self.stdout.write(self.style.SUCCESS(f" [OK] Seeded {len(patient_users)} patients"))

        # 5. Live Queue for Today (Dr. Rahim - Cardiology)
        today = datetime.date.today()
        primary_doctor = doc_profiles[0] # Dr. Rahim

        queue_cases = [
            (patient_users[4], 'completed', 'Chest tightness during physical activity', 'follow_up', 'moderate', True, 24.5, 23.0),
            (patient_users[3], 'completed', 'Routine cardiovascular health check', 'routine_checkup', 'mild', False, 14.0, 15.0),
            (patient_users[0], 'in_consultation', 'Intermittent palpitations and mild fatigue', 'first_visit', 'moderate', False, 18.0, None),
            (patient_users[1], 'waiting', 'High blood pressure readings at home', 'first_visit', 'moderate', True, 22.0, None),
            (patient_users[2], 'scheduled', 'Post-medication ECG review', 'follow_up', 'mild', False, 12.0, None),
        ]

        for token, (pat, status, complaint, vtype, severity, chronic, ml_est, actual) in enumerate(queue_cases, start=1):
            appt, _ = Appointment.objects.get_or_create(
                doctor=primary_doctor,
                appointment_date=today,
                token_number=token,
                defaults={
                    'patient': pat,
                    'appointment_time': datetime.time(9 + token, 0),
                    'visit_type': vtype,
                    'symptom_severity': severity,
                    'has_chronic_condition': chronic,
                    'primary_symptom': complaint,
                    'predicted_duration_minutes': ml_est,
                    'actual_duration_minutes': actual,
                    'status': status,
                    'consultation_started_at': datetime.datetime.now() - datetime.timedelta(minutes=10) if status == 'in_consultation' else None,
                    'doctor_notes': 'Prescribed lifestyle adjustments and anti-hypertensive medication.' if status == 'completed' else '',
                    'prescription': 'Tab. Bisoprolol 2.5mg (1+0+0)\nTab. Aspirin 75mg (0+1+0) after lunch\nFollow up after 2 weeks.' if status == 'completed' else ''
                }
            )
            if status == 'completed':
                PatientFeedback.objects.get_or_create(
                    appointment=appt,
                    defaults={'rating': 5, 'comment': 'Dr. Rahim explained the ECG results thoroughly. Very minimal waiting!'}
                )

        self.stdout.write(self.style.SUCCESS(f" [OK] Seeded Dr. Rahim's live queue for today ({today}) with Token #3 in consultation"))

        # 6. Historical Consultations across past 14 days
        total_historical = 0
        for day_offset in range(1, 15):
            past_date = today - datetime.timedelta(days=day_offset)
            for doc in doc_profiles:
                count_for_day = random.randint(2, 4)
                for t in range(1, count_for_day + 1):
                    pat = random.choice(patient_users)
                    v_type = random.choice(['first_visit', 'follow_up', 'routine_checkup'])
                    severity = random.choice(['mild', 'moderate', 'severe'])
                    chronic = random.choice([True, False])
                    
                    pred_dur = predict_consultation_duration(
                        patient_age=pat.profile.calculated_age,
                        patient_gender=pat.profile.gender,
                        department=doc.department.name,
                        visit_type=v_type,
                        symptom_severity=severity,
                        has_chronic_condition=chronic,
                        doctor_experience_years=doc.experience_years
                    )
                    actual_dur = round(max(8.0, pred_dur + random.uniform(-3.5, 3.5)), 1)
                    
                    hist_appt, created = Appointment.objects.get_or_create(
                        doctor=doc,
                        appointment_date=past_date,
                        token_number=t,
                        defaults={
                            'patient': pat,
                            'appointment_time': datetime.time(9 + (t % 7), 0),
                            'visit_type': v_type,
                            'symptom_severity': severity,
                            'has_chronic_condition': chronic,
                            'primary_symptom': 'Clinical consultation',
                            'predicted_duration_minutes': pred_dur,
                            'actual_duration_minutes': actual_dur,
                            'status': 'completed',
                            'doctor_notes': 'Clinical review completed successfully.',
                            'prescription': 'Tab. Multivitamin once daily\nAdequate hydration.'
                        }
                    )
                    if created:
                        total_historical += 1
                        if random.random() > 0.4:
                            PatientFeedback.objects.get_or_create(
                                appointment=hist_appt,
                                defaults={
                                    'rating': random.choice([4, 5, 5, 4, 5]),
                                    'comment': 'Prompt consultation and accurate waiting time display.'
                                }
                            )

        self.stdout.write(self.style.SUCCESS(f" [OK] Seeded {total_historical} historical completed appointments for ML analytics"))
        self.stdout.write(self.style.SUCCESS("All SmartCare modules seeded successfully!"))

