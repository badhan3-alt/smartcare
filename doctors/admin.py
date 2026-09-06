from django.contrib import admin
from .models import Department, DoctorProfile, DoctorSchedule

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active')
    prepopulated_fields = {'code': ('name',)}

class DoctorScheduleInline(admin.TabularInline):
    model = DoctorSchedule
    extra = 1

@admin.register(DoctorProfile)
class DoctorProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'department', 'qualification', 'experience_years', 'consultation_fee', 'room_number', 'is_available')
    list_filter = ('department', 'is_available')
    search_fields = ('user__first_name', 'user__last_name', 'qualification', 'specialization')
    inlines = [DoctorScheduleInline]

