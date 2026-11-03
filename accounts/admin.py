from django.contrib import admin
from .models import HospitalProfile, UserProfile

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'phone', 'gender', 'blood_group', 'created_at')
    list_filter = ('role', 'gender', 'blood_group')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'phone')
    readonly_fields = ('email_verified',)


@admin.register(HospitalProfile)
class HospitalProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'registration_number', 'user', 'contact_person')
    search_fields = ('name', 'registration_number', 'user__username', 'contact_person')

