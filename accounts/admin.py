from django.contrib import admin
from .models import UserProfile

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'phone', 'gender', 'blood_group', 'created_at')
    list_filter = ('role', 'gender', 'blood_group')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'phone')

